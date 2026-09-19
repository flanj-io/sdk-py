"""THE async contract.

The redaction vectors test strings in, strings out. They say nothing about
``call_tool`` being a coroutine, and no oracle will warn us: capture must not change
timing, must not swallow cancellation, and must not alter how a result behaves.
SDK non-negotiable #2 exists because exactly this bug class shipped once already in
the other runtime - a passive ``on('data')`` listener that broke apps reading bodies
via ``for await``. A fast port reintroduces it in a new runtime.

Every test here is written against a way this wrapper could plausibly be wrong.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from flanj.mcp import instrument_mcp_client


class FakeResult:
    """A CallToolResult-shaped object, the way the official package's model reads."""

    def __init__(self, structured: Any = None, is_error: bool = False, meta: Any = None) -> None:
        self.structuredContent = structured
        self.isError = is_error
        self._meta = meta or {}


class FakeSession:
    """The smallest thing the wrapper instruments: two coroutines and a transport."""

    def __init__(self) -> None:
        self.transport = type("T", (), {"url": "http://mcp.acme.test/mcp"})()
        self.calls: list[str] = []
        self.delay = 0.0
        self.raises: BaseException | None = None
        self.result = FakeResult({"amount": 1200})

    async def call_tool(self, name: str, arguments: Any = None, **kwargs: Any) -> Any:
        self.calls.append(name)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises is not None:
            raise self.raises
        return self.result

    async def list_tools(self, **kwargs: Any) -> Any:
        return type("R", (), {"tools": [{"name": "get_balance"}], "nextCursor": None})()


def instrument(session: Any, **kw: Any) -> list[Any]:
    captured: list[Any] = []
    instrument_mcp_client(session, on_capture=captured.append, **kw)
    return captured


# --- 1. cancellation ----------------------------------------------------------


async def test_cancellation_propagates_untouched_and_is_not_captured() -> None:
    session = FakeSession()
    session.delay = 5.0
    captured = instrument(session)

    task = asyncio.ensure_future(session.call_tool("get_balance", {"account_id": "acct_1"}))
    await asyncio.sleep(0)  # let it reach the await
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert captured == [], "a cancelled call is the caller withdrawing, not an outcome to record"


async def test_cancellation_is_not_delayed_by_capture() -> None:
    session = FakeSession()
    session.delay = 5.0
    instrument(session)

    task = asyncio.ensure_future(session.call_tool("get_balance"))
    await asyncio.sleep(0)
    started = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert time.monotonic() - started < 0.5


async def test_a_cancelled_error_raised_by_the_tool_itself_is_not_swallowed() -> None:
    """Not the same case: here the CALL raises CancelledError rather than the task
    being cancelled. It must still propagate, and still not be recorded as an error
    result - `except Exception` must not reach it."""
    session = FakeSession()
    session.raises = asyncio.CancelledError()
    captured = instrument(session)

    with pytest.raises(asyncio.CancelledError):
        await session.call_tool("get_balance")
    assert captured == []


class CustomBaseException(BaseException):
    """A BaseException that is not an Exception - e.g. trio.Cancelled, KeyboardInterrupt."""


async def test_base_exceptions_pass_through_uncaptured() -> None:
    session = FakeSession()
    session.raises = CustomBaseException("stop")
    captured = instrument(session)

    with pytest.raises(CustomBaseException):
        await session.call_tool("get_balance")
    assert captured == [], "the wrapper must never catch BaseException"


# --- 2. timing ----------------------------------------------------------------


async def test_the_wrapper_adds_no_suspension_point() -> None:
    """An extra `await` - even `sleep(0)` - is an extra place the scheduler can
    interleave, which changes the ordering an app observes. Count the event-loop
    iterations an instrumented call costs against an uninstrumented one.
    """

    async def count_iterations(coro_factory: Any) -> int:
        ticks = 0
        done = False

        async def ticker() -> None:
            nonlocal ticks
            while not done:
                ticks += 1
                await asyncio.sleep(0)

        ticker_task = asyncio.ensure_future(ticker())
        await coro_factory()
        done = True
        await ticker_task
        return ticks

    plain = FakeSession()
    wrapped = FakeSession()
    instrument(wrapped)

    plain_ticks = await count_iterations(lambda: plain.call_tool("get_balance"))
    wrapped_ticks = await count_iterations(lambda: wrapped.call_tool("get_balance"))

    assert wrapped_ticks == plain_ticks, (
        f"instrumented call cost {wrapped_ticks} loop iterations vs {plain_ticks} uninstrumented; "
        "the wrapper introduced a suspension point"
    )


async def test_concurrent_calls_are_not_serialized_by_the_wrapper() -> None:
    session = FakeSession()
    session.delay = 0.05
    instrument(session)

    started = time.monotonic()
    await asyncio.gather(*(session.call_tool(f"tool_{i}") for i in range(8)))
    elapsed = time.monotonic() - started
    assert elapsed < 0.05 * 4, f"8 concurrent 50ms calls took {elapsed:.3f}s - capture serialized them"


# --- 3. pass-through ----------------------------------------------------------


async def test_the_exact_result_object_is_returned_not_a_copy() -> None:
    session = FakeSession()
    instrument(session)
    result = await session.call_tool("get_balance")
    assert result is session.result, "the wrapper must return the tool's own result object"


async def test_arguments_reach_the_tool_verbatim() -> None:
    seen: list[Any] = []

    class Recording(FakeSession):
        async def call_tool(self, name: str, arguments: Any = None, **kwargs: Any) -> Any:
            seen.append((name, arguments, kwargs))
            return self.result

    session = Recording()
    instrument(session)
    sentinel = {"account_id": "acct_1", "nested": {"deep": [1, 2, 3]}}
    await session.call_tool("get_balance", sentinel, read_timeout_seconds=7.5)

    assert seen == [("get_balance", sentinel, {"read_timeout_seconds": 7.5})]
    assert seen[0][1] is sentinel, "arguments must be passed by reference, not re-serialized"


async def test_the_result_is_read_not_consumed() -> None:
    """A result that can only be read once must survive capture intact."""

    class OnceOnly:
        def __init__(self) -> None:
            self.reads = 0
            self.structuredContent = {"amount": 1200}
            self.isError = False

        def __iter__(self) -> Any:
            self.reads += 1
            return iter(())

    session = FakeSession()
    session.result = OnceOnly()  # type: ignore[assignment]
    instrument(session)

    result = await session.call_tool("get_balance")
    assert result.reads == 0, "capture iterated the result; a streamed result would arrive empty"


async def test_a_capture_failure_never_breaks_the_call() -> None:
    session = FakeSession()

    def exploding_sink(_: Any) -> None:
        raise RuntimeError("sink is broken")

    instrument_mcp_client(session, on_capture=exploding_sink)
    result = await session.call_tool("get_balance")
    assert result is session.result, "a broken capture sink must not surface to the app"


async def test_a_tool_error_is_recorded_and_re_raised_untouched() -> None:
    session = FakeSession()
    original = ValueError("upstream refused")
    session.raises = original
    captured = instrument(session)

    with pytest.raises(ValueError) as excinfo:
        await session.call_tool("get_balance")
    assert excinfo.value is original, "the exception object itself must pass through"
    assert len(captured) == 1
    assert captured[0].mcp.is_error is True
    assert captured[0].call.response_body == "", "a failed call has no response body"


async def test_instrumenting_twice_is_a_no_op() -> None:
    session = FakeSession()
    first = instrument(session)
    second = instrument(session)
    await session.call_tool("get_balance")
    assert len(first) == 1 and second == [], "double instrumentation would double every record"


# --- 4. a capture failure is silent to the app, but not invisible to the operator ---


async def test_the_first_capture_failure_warns_once_on_stderr(capsys: Any) -> None:
    """A fenced capture path that fails is silent - and silence is how a user ends up
    believing they have coverage they do not have. One line, once, then nothing.
    """
    from flanj import capture_warning

    capture_warning._reset_for_tests()

    session = FakeSession()

    def exploding_sink(_: Any) -> None:
        raise RuntimeError("sink is broken")

    instrument_mcp_client(session, on_capture=exploding_sink)

    for _ in range(3):
        assert await session.call_tool("get_balance") is session.result

    err = capsys.readouterr().err
    assert err.count("[flanj]") == 1, f"expected exactly one warning, got:\n{err}"
    assert "capture has stopped" in err
    assert "Your application is unaffected" in err
    capture_warning._reset_for_tests()


async def test_the_warning_can_be_silenced(monkeypatch: Any, capsys: Any) -> None:
    from flanj import capture_warning

    capture_warning._reset_for_tests()
    monkeypatch.setenv(capture_warning.SILENCE_ENV, "1")

    session = FakeSession()
    instrument_mcp_client(
        session, on_capture=lambda _: (_ for _ in ()).throw(RuntimeError("x"))
    )
    await session.call_tool("get_balance")

    assert capsys.readouterr().err == ""
    capture_warning._reset_for_tests()
