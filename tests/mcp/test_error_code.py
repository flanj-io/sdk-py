"""`flanj.mcp.error.code`: the JSON-RPC code of a REJECTED tools/call (port of sdk#54).

Set only when the request itself was rejected - never for a result with `isError`,
never for a transport failure. The two `mcp` lines raise different classes
(2.x `MCPError` with `.code`, 1.x `McpError` with `.error.code`); both are covered
with the installed line's REAL class.
"""

from __future__ import annotations

from typing import Any

import pytest

from flanj.mcp import build_mcp_call_attributes, instrument_mcp_client

from ._real import MCP_MAJOR, Server, memory_streams

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _rejection(code: int = -32602) -> BaseException:
    import mcp.shared.exceptions as ex

    cls = getattr(ex, "MCPError", None) or ex.McpError
    try:
        return cls(code=code, message="Invalid params")  # 2.x
    except TypeError:
        from mcp.types import ErrorData

        return cls(ErrorData(code=code, message="Invalid params"))  # 1.x


class _Rejecting:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.transport = type("T", (), {"url": "https://mcp.acme.com/mcp"})()

    async def call_tool(self, name: str, arguments: Any = None, **kw: Any) -> Any:
        raise self.exc


async def test_a_protocol_rejection_records_its_code_on_this_mcp_line() -> None:
    exc = _rejection()
    session = _Rejecting(exc)
    captured: list[Any] = []
    instrument_mcp_client(session, integration="acme-tools", on_capture=captured.append)

    with pytest.raises(type(exc)) as excinfo:
        await session.call_tool("create_refund", {"amount": "1200"})
    assert excinfo.value is exc, "the rejection must pass through as itself"
    assert captured[0].mcp.error_code == -32602
    assert build_mcp_call_attributes(captured[0])["flanj.mcp.error.code"] == -32602


async def test_a_transport_failure_has_no_code() -> None:
    session = _Rejecting(ConnectionError("reset"))
    captured: list[Any] = []
    instrument_mcp_client(session, integration="acme-tools", on_capture=captured.append)
    with pytest.raises(ConnectionError):
        await session.call_tool("get_balance")
    assert captured[0].mcp.error_code is None
    assert "flanj.mcp.error.code" not in build_mcp_call_attributes(captured[0])


async def test_an_is_error_result_is_not_a_rejection() -> None:
    from mcp import ClientSession

    server = Server("acme-tools-mcp")

    @server.tool()
    def get_balance(account_id: str) -> dict[str, Any]:
        return {"amount": 1}

    captured: list[Any] = []
    async with memory_streams(server) as (read, write):
        async with ClientSession(read, write) as session:
            instrument_mcp_client(session, integration="acme-tools", on_capture=captured.append)
            await session.initialize()
            await session.call_tool("get_balance", {})  # missing arg: an isError RESULT
    assert captured[0].mcp.is_error is True
    assert captured[0].mcp.error_code is None


@pytest.mark.skipif(MCP_MAJOR < 2, reason="a 1.x server turns a raised protocol error into an isError result")
async def test_a_real_server_rejection_end_to_end() -> None:
    from mcp import ClientSession

    server = Server("rejecting")

    @server.tool()
    def strict(x: str) -> str:
        raise _rejection()

    captured: list[Any] = []
    async with memory_streams(server) as (read, write):
        async with ClientSession(read, write) as session:
            instrument_mcp_client(session, integration="acme-tools", on_capture=captured.append)
            await session.initialize()
            with pytest.raises(type(_rejection())):
                await session.call_tool("strict", {"x": "a"})
    assert captured[0].mcp.error_code == -32602
