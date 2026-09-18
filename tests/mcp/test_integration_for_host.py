"""Per-server integration ids: the collector's rule, and what happens when it yields nothing.

The vectors are literals shared with the TypeScript suite
(`src/mcp/resolve-mcp-edge.spec.ts`) and match the collector's `integrationForHost`.
"""

from __future__ import annotations

from typing import Any

import pytest

from flanj.mcp import instrument_mcp_client
from flanj.mcp.instrument import UNKNOWN_INTEGRATION, integration_for_host

from ._real import Server, memory_streams

VECTORS = [
    ("api.stripe.com", "api-stripe-com"),
    ("mcp.acme.com:8443", "mcp-acme-com-8443"),
    ("Acme_Tools MCP", "acme-tools-mcp"),
    ("--weird..host--", "weird-host"),
    ("café-mcp", "caf-mcp"),
    ("天气", ""),
]


@pytest.mark.parametrize("host,expected", VECTORS)
def test_the_collectors_rule(host: str, expected: str) -> None:
    assert integration_for_host(host) == expected


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _integration_of(server_name: str, **options: Any) -> str:
    from mcp import ClientSession

    server = Server(server_name)

    @server.tool()
    def ping() -> str:
        return "pong"

    captured: list[Any] = []
    async with memory_streams(server) as (read, write):
        async with ClientSession(read, write) as session:
            instrument_mcp_client(session, server_kind="stdio", on_capture=captured.append, **options)
            await session.initialize()
            await session.call_tool("ping", {})
    return str(captured[0].call.integration)


@pytest.mark.anyio
async def test_a_server_name_with_nothing_to_slug_falls_back_rather_than_emitting_empty() -> None:
    assert await _integration_of("天气") == UNKNOWN_INTEGRATION


@pytest.mark.anyio
async def test_a_configured_integration_always_wins() -> None:
    assert await _integration_of("天气", integration="acme-weather") == "acme-weather"
