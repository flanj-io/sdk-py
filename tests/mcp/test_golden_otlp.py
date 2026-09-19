"""The WIRE seam: what this SDK emits must be exactly what the collector expects.

``contracts/golden-otlp-mcp-call.json`` and ``contracts/golden-otlp-mcp-snapshot.json``
are vendored byte-identically from the canonical contract source, and the
TypeScript SDK asserts against the same two files. These tests are how "the Python
SDK speaks the same wire format" stops being a claim and becomes a check - the
alternative is finding out in the integration gate, after a merge.

The assertion is on the FULL attribute map, both directions: no expected attribute
missing, and no unexpected attribute added. A test that only checks the keys it
thinks of is how an extra attribute reaches a collector that was never asked about
it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flanj.mcp import build_contract_snapshot_attributes, build_mcp_call_attributes
from flanj.mcp.assemble_call import assemble_mcp_call
from flanj.mcp.assemble_snapshot import assemble_contract_snapshot
from flanj.mcp.types import McpServerIdentity

CONTRACTS = Path(__file__).resolve().parent.parent.parent / "contracts"


def golden_attributes(filename: str) -> dict[str, Any]:
    """The golden record's attributes, flattened out of the OTLP any-value wrapping."""
    doc = json.loads((CONTRACTS / filename).read_text(encoding="utf-8"))
    record = doc["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    out: dict[str, Any] = {}
    for attr in record["attributes"]:
        value = attr["value"]
        kind = next(iter(value))
        raw = value[kind]
        if kind == "intValue":
            raw = int(raw)
        elif kind == "doubleValue":
            raw = float(raw)
        out[attr["key"]] = raw
    return out


def test_mcp_tool_call_record_matches_the_golden_record() -> None:
    captured = assemble_mcp_call(
        integration="acme-payments",
        peer_host="mcp.acme.test",
        edge_class="external",
        server_kind="streamable-http",
        tool_name="create_refund",
        args={"amount": 1200, "card_number": "4111111111111111", "currency": "usd"},
        result={
            "structuredContent": {
                "refund": {"id": "re_71", "amount": "1200", "status": "succeeded"}
            }
        },
        is_error=False,
        server_name="acme-payments-mcp",
        server_version="3.2.0",
        protocol_version="2025-06-18",
        session_id="sess_9f3c1a",
        client_request_id="4",
        duration_ms=18,
    )
    actual = build_mcp_call_attributes(captured)
    expected = golden_attributes("golden-otlp-mcp-call.json")

    assert actual == expected


def test_the_call_record_carries_no_http_status_code() -> None:
    """MCP has no status codes; `flanj.mcp.is_error` carries the outcome. The HTTP
    mapping supplies one, so the MCP mapping must remove it - and a reader that sees
    `flanj.http.status_code: 0` would record a successful call as an error.
    """
    captured = assemble_mcp_call(
        integration="acme-tools",
        peer_host="mcp.acme.test",
        edge_class="external",
        server_kind="streamable-http",
        tool_name="get_balance",
        args={},
        result={"structuredContent": {"amount": 1}},
        is_error=False,
        duration_ms=1,
    )
    assert "flanj.http.status_code" not in build_mcp_call_attributes(captured)


def test_contract_snapshot_record_matches_the_golden_record() -> None:
    snapshot = assemble_contract_snapshot(
        integration="acme-payments",
        peer_host="mcp.acme.test",
        edge_class="external",
        server_kind="streamable-http",
        server=McpServerIdentity(
            name="acme-payments-mcp",
            version="3.2.0",
            protocol_version="2025-06-18",
            list_changed=True,
        ),
        tools=json.loads(_golden_snapshot_tools()),
    )
    actual = build_contract_snapshot_attributes(snapshot)
    expected = golden_attributes("golden-otlp-mcp-snapshot.json")

    assert actual == expected


def _golden_snapshot_tools() -> str:
    """The tools array the golden snapshot encodes, fed back in as the server's words.

    Round-tripping the golden document is the point: it proves the projection onto
    the ToolDef wire keys is lossless and key-order-stable, which a hand-written
    fixture could not.
    """
    doc = golden_attributes("golden-otlp-mcp-snapshot.json")
    return json.dumps(json.loads(doc["flanj.mcp.contract_snapshot"])["tools"])


def test_a_tool_without_an_output_schema_keeps_none() -> None:
    """The honest "no output contract declared" state, never synthesized."""
    snapshot = assemble_contract_snapshot(
        integration="acme-tools",
        peer_host="mcp.acme.test",
        edge_class="external",
        server_kind="streamable-http",
        server=McpServerIdentity(),
        tools=[{"name": "list_transactions", "description": "Recent transactions."}],
    )
    document = json.loads(snapshot.snapshot_json)
    assert document["tools"] == [
        {"name": "list_transactions", "description": "Recent transactions."}
    ]
    assert "outputSchema" not in document["tools"][0]


def test_the_snapshot_is_floor_redacted_before_it_is_emitted() -> None:
    """Schemas are the server's words, but a server can put a card number in a
    description - the snapshot crosses the wire only as redacted text.
    """
    snapshot = assemble_contract_snapshot(
        integration="acme-tools",
        peer_host="mcp.acme.test",
        edge_class="external",
        server_kind="streamable-http",
        server=McpServerIdentity(),
        tools=[{"name": "pay", "description": "e.g. card 4111111111111111"}],
    )
    assert "4111111111111111" not in snapshot.snapshot_json
    assert "⟦REDACTED:PAN⟧" in snapshot.snapshot_json
    assert snapshot.redaction_applied is True
    assert snapshot.redaction_patterns == ["PAN"]
