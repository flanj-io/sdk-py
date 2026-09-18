"""Identity and correlation on a REAL session, on whichever mcp line is installed.

Regression for two bugs that only the 1.x line showed: `serverInfo` is discarded
after the handshake (so every stdio server collapsed onto `unknown-mcp-server`), and
there is no dispatcher to observe the client's JSON-RPC ids on. CI runs this file on
both lines.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from flanj.mcp import instrument_mcp_client
from flanj.mcp.transports import patch_transport_openers, unpatch_transport_openers

from ._real import MCP_MAJOR, SERVER_NAME, write_server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _capture(tmp: Path) -> Any:
    import mcp.client.stdio as stdio
    from mcp import ClientSession

    patch_transport_openers()
    try:
        params = stdio.StdioServerParameters(command=sys.executable, args=[str(write_server(tmp))])
        captured: list[Any] = []
        async with stdio.stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                instrument_mcp_client(session, integration="acme-tools", on_capture=captured.append)
                await session.initialize()
                await session.call_tool("get_balance", {"account_id": "acct_1"})
        return captured[0]
    finally:
        unpatch_transport_openers()


async def test_server_identity_survives_the_handshake(tmp_path: Path) -> None:
    captured = await _capture(tmp_path)
    assert captured.mcp.server_name == SERVER_NAME, f"mcp {MCP_MAJOR}.x lost the server's name"
    assert captured.call.peer_host == SERVER_NAME


async def test_the_client_request_id_is_observed(tmp_path: Path) -> None:
    captured = await _capture(tmp_path)
    assert captured.mcp.client_request_id is not None, (
        f"no JSON-RPC id observed on the mcp {MCP_MAJOR}.x line"
    )
    assert captured.mcp.client_request_id.isdigit()
