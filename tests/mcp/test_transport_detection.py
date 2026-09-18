"""Where is the MCP server? Detection against REAL servers and transports.

A Python `ClientSession` holds two in-memory streams and no URL. The SDK learns
where a server is when its transport OPENS (`flanj.mcp.transports`), and a session
whose transport it never saw is `unknown` - recorded without bodies, and said so
once - never guessed. Before this, the README's own quick start filed a remote HTTP
server as a local stdio process, and an internal server's bodies were exported.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from flanj import capture_warning
from flanj.mcp import instrument_mcp_client
from flanj.mcp.transports import patch_transport_openers, unpatch_transport_openers

from ._real import SERVER_NAME, build_server, http_server, memory_streams, write_server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def patched() -> Any:
    patch_transport_openers()
    capture_warning._reset_for_tests()
    yield
    unpatch_transport_openers()
    capture_warning._reset_for_tests()


async def _one_call(read: Any, write: Any, **instrument: Any) -> Any:
    from mcp import ClientSession

    captured: list[Any] = []
    async with ClientSession(read, write) as session:
        instrument_mcp_client(session, on_capture=captured.append, **instrument)
        await session.initialize()
        await session.call_tool("get_balance", {"account_id": "acct_1"})
    assert len(captured) == 1
    return captured[0]


async def test_a_remote_http_server_is_placed_by_its_host(patched: Any, tmp_path: Path) -> None:
    import mcp.client.streamable_http as sh

    opener = getattr(sh, "streamable_http_client", None) or sh.streamablehttp_client
    with http_server(tmp_path) as url:
        async with opener(url) as streams:
            captured = await _one_call(streams[0], streams[1], integration="acme-tools")

    host = url.split("/")[2]
    assert captured.call.peer_host == host, "keyed by server name instead of its host"
    assert captured.mcp.server_kind == "streamable-http"
    # 127.0.0.1 is loopback: INTERNAL, so its bodies must not be read at all.
    assert captured.call.edge_class == "internal"
    assert captured.call.response_body == "", "an internal server's body was captured"
    assert captured.call.capture_bodies is False


async def test_a_stdio_server_is_a_local_process_keyed_by_its_name(patched: Any, tmp_path: Path) -> None:
    import mcp.client.stdio as stdio

    params = stdio.StdioServerParameters(command=sys.executable, args=[str(write_server(tmp_path))])
    async with stdio.stdio_client(params) as (read, write):
        captured = await _one_call(read, write, integration="acme-tools")

    assert captured.call.edge_class == "local-process"
    assert captured.call.peer_host == SERVER_NAME, "the stdio edge lost the server's identity"
    assert "⟦REDACTED:PAN⟧" in captured.call.response_body, "a local process's body is evidence"


async def test_a_transport_flanj_never_saw_is_unknown_without_bodies_and_says_so(
    patched: Any, capsys: Any
) -> None:
    async with memory_streams(build_server()) as (read, write):
        captured = await _one_call(read, write, integration="acme-tools")

    assert captured.call.edge_class == "unknown"
    assert captured.mcp.server_kind == "unknown"
    assert captured.call.response_body == "", "an unplaceable server's body was captured"
    err = capsys.readouterr().err
    assert err.count("[flanj] could not tell whether MCP server") == 1
    assert "load flanj first" in err and "endpoint=" in err


async def test_an_opener_bound_before_flanj_loaded_is_not_seen(tmp_path: Path, capsys: Any) -> None:
    """The load-order rule, proved: a pre-bound opener bypasses detection."""
    import mcp.client.stdio as stdio

    capture_warning._reset_for_tests()
    early_bound = stdio.stdio_client  # the app imported it before flanj loaded
    patch_transport_openers()
    try:
        params = stdio.StdioServerParameters(command=sys.executable, args=[str(write_server(tmp_path))])
        async with early_bound(params) as (read, write):
            captured = await _one_call(read, write, integration="acme-tools")
    finally:
        unpatch_transport_openers()
    assert captured.call.edge_class == "unknown"
    assert "load flanj first" in capsys.readouterr().err


async def test_explicit_config_still_wins(patched: Any) -> None:
    async with memory_streams(build_server()) as (read, write):
        captured = await _one_call(
            read, write, integration="acme-tools", endpoint="https://mcp.acme.com/mcp"
        )
    assert captured.call.peer_host == "mcp.acme.com"
    assert captured.call.edge_class == "external"


async def test_the_opener_wrapper_is_transparent() -> None:
    """The caller gets the opener's OWN streams, and its exceptions untouched."""
    import contextlib

    from flanj.mcp.transports import _url_tag, _wrap, tag_of

    class Stream:
        pass

    streams = (Stream(), Stream())
    boom = RuntimeError("transport failed")

    @contextlib.asynccontextmanager
    async def opener(url: str, fail: bool = False) -> Any:
        if fail:
            raise boom
        yield streams

    wrapped = _wrap(opener, _url_tag)
    async with wrapped("https://mcp.acme.com/mcp") as got:
        assert got is streams, "the wrapper must hand back the opener's own tuple"
        assert tag_of(got[1]).url == "https://mcp.acme.com/mcp"

    with pytest.raises(RuntimeError) as excinfo:
        async with wrapped("https://x", fail=True):
            pass
    assert excinfo.value is boom, "the opener's exception must pass through as itself"
