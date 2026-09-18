"""Auto-instrumentation: patch the session class once; every session instruments itself.

The counterpart of the TypeScript SDK's `patchMcpClientConstructor`. Checked on a
real session (no manual `instrument_mcp_client` call anywhere), plus the properties
the trampolines must not break: idempotence, and no added suspension point.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

from flanj.mcp.auto import (
    patch_client_session_class,
    register_mcp_auto_instrumentation,
    unregister_mcp_auto_instrumentation,
)
from flanj.mcp.instrument import integration_for_host

from ._real import SERVER_NAME, write_server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _session_calls(tmp: Path, calls: int = 1) -> None:
    import mcp.client.stdio as stdio
    from mcp import ClientSession

    params = stdio.StdioServerParameters(command=sys.executable, args=[str(write_server(tmp))])
    async with stdio.stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.list_tools()
            for _ in range(calls):
                await session.call_tool("get_balance", {"account_id": "acct_1"})


async def test_a_session_nobody_instrumented_is_captured(tmp_path: Path) -> None:
    captured: list[Any] = []
    snapshots: list[Any] = []
    patched = register_mcp_auto_instrumentation(on_capture=captured.append, on_snapshot=snapshots.append)
    try:
        assert "mcp.client.session.ClientSession" in patched
        await _session_calls(tmp_path)
    finally:
        unregister_mcp_auto_instrumentation()

    assert len(captured) == 1 and len(snapshots) == 1
    call = captured[0]
    assert call.call.edge_class == "local-process", "auto path did not detect the stdio transport"
    assert call.mcp.server_name == SERVER_NAME
    # No integration configured: each server gets its own, the collector's way.
    assert call.call.integration == integration_for_host(SERVER_NAME) == "acme-tools-mcp"


async def test_registering_twice_captures_each_call_once(tmp_path: Path) -> None:
    captured: list[Any] = []
    register_mcp_auto_instrumentation(on_capture=captured.append)
    register_mcp_auto_instrumentation(on_capture=captured.append)
    try:
        await _session_calls(tmp_path, calls=2)
    finally:
        unregister_mcp_auto_instrumentation()
    assert len(captured) == 2


async def test_unregister_restores_the_class(tmp_path: Path) -> None:
    from mcp.client.session import ClientSession

    before = ClientSession.call_tool
    register_mcp_auto_instrumentation(on_capture=lambda _: None)
    assert ClientSession.call_tool is not before
    unregister_mcp_auto_instrumentation()
    assert ClientSession.call_tool is before


class _Session:
    """A class shaped like ClientSession, to test the trampoline in isolation."""

    def __init__(self) -> None:
        self.transport = type("T", (), {"url": "https://mcp.acme.com/mcp"})()
        self.result = {"structuredContent": {"amount": 1}}

    async def initialize(self) -> Any:
        return {"serverInfo": {"name": "x"}}

    async def list_tools(self, **kwargs: Any) -> Any:
        return {"tools": [], "nextCursor": None}

    async def call_tool(self, name: str, arguments: Any = None, **kwargs: Any) -> Any:
        return self.result


async def test_the_trampoline_returns_the_tools_own_result_and_adds_no_suspension_point() -> None:
    plain = _Session()

    class Patched(_Session):
        pass

    captured: list[Any] = []
    assert patch_client_session_class(Patched, integration="acme-tools", on_capture=captured.append)
    wrapped = Patched()

    async def ticks(coro_factory: Any) -> int:
        count = 0
        done = False

        async def ticker() -> None:
            nonlocal count
            while not done:
                count += 1
                await asyncio.sleep(0)

        task = asyncio.ensure_future(ticker())
        await coro_factory()
        done = True
        await task
        return count

    assert (await wrapped.call_tool("get_balance")) is wrapped.result
    assert len(captured) == 1
    assert await ticks(lambda: wrapped.call_tool("x")) == await ticks(lambda: plain.call_tool("x"))
