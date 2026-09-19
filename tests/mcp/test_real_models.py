"""Capture against the OFFICIAL package's own pydantic models, not dicts.

REGRESSION. Every other test in this suite hands the wrapper plain dicts with the
protocol's WIRE names (``structuredContent``, ``isError``, ``nextCursor``). The real
``mcp`` package models the protocol with pydantic and exposes those fields under
their PYTHON names (``structured_content``, ``is_error``, ``next_cursor``) - the
camelCase spelling is only a serialization alias, and is not an attribute at all.

So a reader that used the wire name alone returned ``None`` for every real client,
captured an EMPTY response body, and left the whole unit suite green. It was the
stranger smoke (`scripts/smoke-pack.sh`) that caught it, which is precisely the gap
that script exists to cover - and this file is what stops it needing to catch it
twice.
"""

from __future__ import annotations

from typing import Any

import pytest

from flanj.mcp import instrument_mcp_client

mcp_types = pytest.importorskip("mcp.types", reason="the official mcp package is a dev dependency")


def build_call_tool_result(structured: Any, is_error: bool = False) -> Any:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="mirrored")],
        structuredContent=structured,
        isError=is_error,
    )


class ModelSession:
    """A session whose coroutines return real protocol models."""

    def __init__(self, result: Any, tools: list[Any]) -> None:
        self._result = result
        self._tools = tools
        self.transport = type("T", (), {"url": "http://mcp.acme.test/mcp"})()

    async def call_tool(self, name: str, arguments: Any = None, **kwargs: Any) -> Any:
        return self._result

    async def list_tools(self, **kwargs: Any) -> Any:
        return mcp_types.ListToolsResult(tools=self._tools)


def instrument(session: Any) -> tuple[list[Any], list[Any]]:
    calls: list[Any] = []
    snapshots: list[Any] = []
    instrument_mcp_client(
        session, on_capture=calls.append, on_snapshot=snapshots.append
    )
    return calls, snapshots


async def test_structured_content_is_captured_from_a_real_model() -> None:
    session = ModelSession(
        build_call_tool_result({"amount": 1200, "card_number": "4111111111111111"}), []
    )
    calls, _ = instrument(session)

    await session.call_tool("get_balance", {"account_id": "acct_1"})

    assert len(calls) == 1
    body = calls[0].call.response_body
    assert body != "", "the response body was empty - a wire-name-only read returns None here"
    assert "4111111111111111" not in body
    assert "⟦REDACTED:PAN⟧" in body
    assert calls[0].call.response_content_type == "application/json"
    assert calls[0].call.redaction_patterns == ["PAN"]


async def test_is_error_is_read_from_a_real_model() -> None:
    session = ModelSession(build_call_tool_result({"ok": False}, is_error=True), [])
    calls, _ = instrument(session)

    await session.call_tool("get_balance")

    assert calls[0].mcp.is_error is True, "an errored tool result was recorded as a success"


async def test_content_text_is_captured_when_there_is_no_structured_content() -> None:
    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="card 4111111111111111")]
    )
    session = ModelSession(result, [])
    calls, _ = instrument(session)

    await session.call_tool("list_transactions")

    assert calls[0].call.response_content_type == "text/plain"
    assert "⟦REDACTED:PAN⟧" in calls[0].call.response_body


async def test_tool_schemas_survive_the_projection_from_a_real_model() -> None:
    tools = [
        mcp_types.Tool(
            name="get_balance",
            description="Current balance for an account.",
            inputSchema={"type": "object", "properties": {"account_id": {"type": "string"}}},
            outputSchema={"type": "object", "properties": {"amount": {"type": "integer"}}},
        ),
        # The honest "no output contract declared" tool.
        mcp_types.Tool(name="list_transactions", inputSchema={"type": "object"}),
    ]
    session = ModelSession(build_call_tool_result({}), tools)
    _, snapshots = instrument(session)

    await session.list_tools()

    assert len(snapshots) == 1
    import json

    document = json.loads(snapshots[0].snapshot_json)
    assert snapshots[0].tool_count == 2
    first, second = document["tools"]
    assert first["name"] == "get_balance"
    assert first["inputSchema"]["properties"]["account_id"] == {"type": "string"}
    assert first["outputSchema"]["properties"]["amount"] == {"type": "integer"}
    assert "outputSchema" not in second, "an absent output schema must never be synthesized"
