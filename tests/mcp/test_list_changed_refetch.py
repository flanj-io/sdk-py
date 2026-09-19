"""`tools/list_changed` -> refetch -> a fresh contract snapshot, against a REAL server.

Default ON, the same as the TypeScript SDK's ``refetchOnListChanged``. The two
defaults have to match: a Python tenant and a Node tenant watching one MCP server
must build the same baseline, and a divergent default would make them differ
silently - one layer above anything the shared redaction fixtures can see.

These tests drive the official ``mcp`` package end to end over its in-memory
transport: a real ``MCPServer`` adds a tool at runtime and sends a real
``notifications/tools/list_changed``; a real ``ClientSession`` receives it. Nothing
here is a dict pretending to be a model - the wire-name/python-name bug in this
SDK was only visible that way.
"""

from __future__ import annotations

from typing import Any

import anyio
import pytest

from flanj.mcp import instrument_mcp_client

mcp = pytest.importorskip("mcp", reason="the official mcp package is a dev dependency")

from mcp import ClientSession  # noqa: E402

from ._real import Server, memory_streams  # noqa: E402

try:  # 2.x
    from mcp.server.mcpserver import Context
except ImportError:  # 1.x
    from mcp.server.fastmcp import Context  # type: ignore[no-redef]

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def build_server() -> Any:
    server = Server("acme-tools-mcp")

    @server.tool()
    def get_balance(account_id: str) -> dict[str, Any]:
        """Current balance for an account."""
        return {"amount": 1200}

    @server.tool()
    async def publish_v2(ctx: Context) -> str:
        """Add a tool at runtime and announce it, the way a deploy would."""

        def get_account_balance(account_id: str) -> dict[str, Any]:
            """The renamed balance tool."""
            return {"amount": 1200}

        server.add_tool(get_account_balance)
        await ctx.request_context.session.send_tool_list_changed()
        return "published"

    return server


async def snapshots_after_announcement(**instrument_kwargs: Any) -> list[Any]:
    snapshots: list[Any] = []
    arrived = anyio.Event()

    def on_snapshot(snap: Any) -> None:
        snapshots.append(snap)
        if len(snapshots) >= 2:
            arrived.set()

    async with memory_streams(build_server()) as (read, write):
        async with ClientSession(read, write) as session:
            instrument_mcp_client(
                session, on_snapshot=on_snapshot, **instrument_kwargs
            )
            await session.initialize()
            await session.list_tools()  # snapshot 1: the app's own list
            await session.call_tool("publish_v2", {})  # server adds a tool + announces
            with anyio.move_on_after(5):
                await arrived.wait()
    return snapshots


async def test_the_default_refetches_on_list_changed_and_snapshots_the_new_catalogue() -> None:
    snapshots = await snapshots_after_announcement()

    assert len(snapshots) == 2, (
        "no second snapshot: the list_changed announcement did not trigger a refetch"
    )
    assert '"get_account_balance"' not in snapshots[0].snapshot_json
    assert '"get_account_balance"' in snapshots[1].snapshot_json, (
        "the refetched snapshot missed the announced tool"
    )
    assert snapshots[1].tool_count == snapshots[0].tool_count + 1


async def test_the_default_matches_the_typescript_sdk() -> None:
    """Pinned directly, so a future edit to the default is a deliberate, visible act."""
    import inspect

    default = inspect.signature(instrument_mcp_client).parameters["refetch_on_list_changed"].default
    assert default is True


async def test_opting_out_takes_no_second_snapshot() -> None:
    snapshots = await snapshots_after_announcement(refetch_on_list_changed=False)
    assert len(snapshots) == 1


async def test_the_applications_own_message_handler_still_runs() -> None:
    """Chained, never replaced: the app keeps receiving every notification."""
    seen: list[str] = []

    async def app_handler(message: Any) -> None:
        # The 1.x line hands the handler a `ServerNotification` wrapper, with the
        # method on `.root`; 2.x hands the notification itself.
        method = getattr(message, "method", None) or getattr(getattr(message, "root", None), "method", None)
        if isinstance(method, str):
            seen.append(method)

    arrived = anyio.Event()
    snapshots: list[Any] = []

    def on_snapshot(snap: Any) -> None:
        snapshots.append(snap)
        if len(snapshots) >= 2:
            arrived.set()

    async with memory_streams(build_server()) as (read, write):
        async with ClientSession(read, write, message_handler=app_handler) as session:
            instrument_mcp_client(session, on_snapshot=on_snapshot)
            await session.initialize()
            await session.list_tools()
            await session.call_tool("publish_v2", {})
            with anyio.move_on_after(5):
                await arrived.wait()

    assert "notifications/tools/list_changed" in seen, "the app's handler stopped receiving notifications"
    assert len(snapshots) == 2


async def test_a_cursor_page_uses_the_shape_this_client_line_accepts() -> None:
    """Page 2+ of a refetch must not TypeError: mcp 2.x takes `params=`, not `cursor=`.

    Regression: the refetch called `list_tools(cursor=...)`, which the 2.x line
    rejects, inside a fenced task - so every refetch after its first page would have
    ended silently.
    """
    from flanj.mcp.instrument import _list_tools_page

    captured: dict[str, Any] = {}

    class TwoLineSession:
        async def list_tools(self, *, params: Any = None) -> Any:
            captured["params"] = params
            return None

    await _list_tools_page(TwoLineSession(), "c2")
    assert getattr(captured["params"], "cursor", None) == "c2"

    class OneLineSession:
        async def list_tools(self, cursor: Any = None) -> Any:
            captured["cursor"] = cursor
            return None

    await _list_tools_page(OneLineSession(), "c3")
    assert captured["cursor"] == "c3"
