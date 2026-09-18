"""Real MCP servers for tests, on whichever `mcp` package line is installed.

CI runs the suite on both the 1.x and the 2.x line, and their test helpers differ
(2.x: `MCPServer`, `InMemoryTransport`; 1.x: `FastMCP`, neither of those). This
module picks the matching primitives so each test is written once. Everything here
is a REAL server speaking the real protocol - the wire-name/python-name bug this
SDK once shipped was only visible that way.
"""

from __future__ import annotations

import contextlib
import importlib.metadata
import socket
import subprocess
import sys
import textwrap
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import anyio

MCP_VERSION = importlib.metadata.version("mcp")
MCP_MAJOR = int(MCP_VERSION.split(".")[0])

try:  # 2.x
    from mcp.server.mcpserver import MCPServer as Server

    _LOWLEVEL = "_lowlevel_server"
except ImportError:  # 1.x
    from mcp.server.fastmcp import FastMCP as Server  # type: ignore[no-redef]

    _LOWLEVEL = "_mcp_server"

SERVER_NAME = "acme-tools-mcp"

#: A server module usable as a stdio child process or an HTTP app, on either line.
SERVER_SOURCE = textwrap.dedent(
    f"""
    import sys
    try:
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:
        from mcp.server.fastmcp import FastMCP as Server

    server = Server({SERVER_NAME!r})

    @server.tool()
    def get_balance(account_id: str) -> dict:
        '''Current balance for an account.'''
        return {{"account_id": account_id, "amount": 1200, "card_number": "4111111111111111"}}

    if __name__ == "__main__":
        if len(sys.argv) > 1:
            import uvicorn
            uvicorn.run(server.streamable_http_app(), host="127.0.0.1", port=int(sys.argv[1]),
                        log_level="warning")
        else:
            server.run()
    """
)


def build_server() -> Any:
    server = Server(SERVER_NAME)

    @server.tool()
    def get_balance(account_id: str) -> dict[str, Any]:
        """Current balance for an account."""
        return {"account_id": account_id, "amount": 1200, "card_number": "4111111111111111"}

    return server


@contextlib.asynccontextmanager
async def memory_streams(server: Any) -> AsyncIterator[tuple[Any, Any]]:
    """An in-process connection with NO transport opener involved - the 'unknown' case."""
    from mcp.shared.memory import create_client_server_memory_streams

    low = getattr(server, _LOWLEVEL)
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                lambda: low.run(server_streams[0], server_streams[1], low.create_initialization_options())
            )
            try:
                yield client_streams[0], client_streams[1]
            finally:
                tg.cancel_scope.cancel()


def write_server(tmp: Path) -> Path:
    path = tmp / "server.py"
    path.write_text(SERVER_SOURCE)
    return path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextlib.contextmanager
def http_server(tmp: Path) -> Iterator[str]:
    """A real streamable-HTTP MCP server in a subprocess. Yields its URL."""
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, str(write_server(tmp)), str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        else:
            raise RuntimeError("the test MCP server did not start")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        proc.wait(timeout=10)
