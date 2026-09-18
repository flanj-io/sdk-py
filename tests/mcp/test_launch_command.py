"""`flanj.mcp.server.command`: the encoding, the redaction, the cap, and the real path.

The encoding is specified to the byte in CONTRACTS section 2 because the TypeScript
SDK must emit the identical string. The literal expectations below are duplicated in
the TypeScript suite (`src/mcp/launch-command.spec.ts`); if one side changes, the
other must.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from flanj.mcp import instrument_mcp_client
from flanj.mcp.launch import ELLIPSIS, MAX_COMMAND_BYTES, launch_command_attribute
from flanj.mcp.record import build_contract_snapshot_attributes
from flanj.mcp.transports import patch_transport_openers, unpatch_transport_openers

from ._real import http_server, write_server

# --- the shared vectors (identical literals in the TypeScript suite) -----------

VECTORS = [
    (("npx", ["-y", "@stripe/mcp@0.2.1", "--tools=all"]), '["npx","-y","@stripe/mcp@0.2.1","--tools=all"]'),
    (("uvx", ["mcp-server-fetch"]), '["uvx","mcp-server-fetch"]'),
    (("node", []), '["node"]'),
    # A secret in an argument is floor-redacted on its own, before the array is built.
    (
        ("npx", ["@stripe/mcp", "--api-key=sk_live_FAKEfixtureKEY0001"]),
        '["npx","@stripe/mcp","--api-key=⟦REDACTED:TOKEN⟧"]',
    ),
    # Non-ASCII is written raw, as JSON.stringify does.
    (("npx", ["café-mcp"]), '["npx","café-mcp"]'),
]


@pytest.mark.parametrize("launch,expected", VECTORS)
def test_the_encoding_matches_the_shared_vectors(launch: Any, expected: str) -> None:
    command, args = launch
    assert launch_command_attribute(command, args) == expected


def test_arguments_past_the_cap_are_dropped_and_marked() -> None:
    args = [f"--flag-{i:03d}=" + "x" * 40 for i in range(60)]
    value = launch_command_attribute("npx", args)
    assert value is not None
    assert len(value.encode("utf-8")) <= MAX_COMMAND_BYTES
    decoded = json.loads(value)
    assert decoded[0] == "npx"
    assert decoded[-1] == ELLIPSIS
    assert decoded[1:-1] == args[: len(decoded) - 2], "kept elements must be the leading ones, in order"
    # One more element would not have fit with the closing marker.
    next_arg = args[len(decoded) - 2]
    one_more = json.dumps([*decoded[:-1], next_arg, ELLIPSIS], ensure_ascii=False, separators=(",", ":"))
    assert len(one_more.encode("utf-8")) > MAX_COMMAND_BYTES


def test_a_command_too_long_to_carry_is_omitted_not_truncated() -> None:
    assert launch_command_attribute("x" * 2000, ["a"]) is None


def test_nothing_to_record_without_a_command() -> None:
    assert launch_command_attribute("", ["a"]) is None


# --- the real path -----------------------------------------------------------

@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _snapshot(streams: Any) -> Any:
    from mcp import ClientSession

    snapshots: list[Any] = []
    async with ClientSession(streams[0], streams[1]) as session:
        instrument_mcp_client(session, integration="acme-tools", on_snapshot=snapshots.append)
        await session.initialize()
        await session.list_tools()
    return snapshots[0]


@pytest.mark.anyio
async def test_a_stdio_snapshot_carries_how_the_server_was_launched(tmp_path: Path) -> None:
    import mcp.client.stdio as stdio

    patch_transport_openers()
    try:
        script = str(write_server(tmp_path))
        params = stdio.StdioServerParameters(command=sys.executable, args=[script], env={"SECRET": "x"})
        async with stdio.stdio_client(params) as streams:
            snapshot = await _snapshot(streams)
    finally:
        unpatch_transport_openers()
    assert json.loads(snapshot.server_command) == [sys.executable, script]
    attrs = build_contract_snapshot_attributes(snapshot)
    assert attrs["flanj.mcp.server.command"] == snapshot.server_command
    assert "SECRET" not in snapshot.server_command, "the environment must never be recorded"


@pytest.mark.anyio
async def test_a_url_addressed_snapshot_carries_no_command(tmp_path: Path) -> None:
    import mcp.client.streamable_http as sh

    patch_transport_openers()
    try:
        opener = getattr(sh, "streamable_http_client", None) or sh.streamablehttp_client
        with http_server(tmp_path) as url:
            async with opener(url) as streams:
                snapshot = await _snapshot(streams)
    finally:
        unpatch_transport_openers()
    assert snapshot.server_command is None
    assert "flanj.mcp.server.command" not in build_contract_snapshot_attributes(snapshot)
