"""Assemble the ``contract_snapshot`` payload for one COMPLETE observed ``tools/list``.

The full tools array projected onto the ToolDef wire keys the collector's loader
decodes (``name/description/inputSchema/outputSchema/annotations``), plus server
identity - then floor-redacted as one JSON text before anything is attached or
emitted. Schemas are the server's own words: passed through verbatim, never
re-inferred; a tool without ``outputSchema`` keeps none (the honest "no output
contract declared" state).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from ..redaction import redact_detailed
from .assemble_call import _plain
from .result_meta import CatalogCacheHints, get_field
from .types import EdgeClass, McpContractSnapshot, McpServerIdentity, McpServerKind


def assemble_contract_snapshot(
    *,
    integration: str,
    peer_host: str,
    edge_class: EdgeClass,
    server_kind: McpServerKind,
    server: McpServerIdentity,
    tools: Sequence[Any],
    cache: CatalogCacheHints | None = None,
) -> McpContractSnapshot:
    defs = [d for d in (_to_tool_def(t) for t in tools) if d is not None]

    payload: dict[str, Any] = {"tools": defs}
    if server.name is not None or server.version is not None:
        server_info: dict[str, Any] = {}
        if server.name is not None:
            server_info["name"] = server.name
        if server.version is not None:
            server_info["version"] = server.version
        payload["serverInfo"] = server_info
    if server.protocol_version is not None:
        payload["protocolVersion"] = server.protocol_version
    if server.list_changed is not None:
        payload["capabilities"] = {"tools": {"listChanged": server.list_changed}}
    # Cache directives ride INSIDE the document as well as on the record, so the
    # stored snapshot stays self-describing: a reader holding only the doc can still
    # tell how stale the catalog it is checking against may be.
    if cache is not None and cache.ttl_ms is not None:
        payload["ttlMs"] = cache.ttl_ms
    if cache is not None and cache.cache_scope is not None:
        payload["cacheScope"] = cache.cache_scope

    # Redact-at-source: the snapshot crosses the wire only as this redacted text.
    redaction = redact_detailed(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    return McpContractSnapshot(
        integration=integration,
        peer_host=peer_host,
        edge_class=edge_class,
        server_kind=server_kind,
        snapshot_json=redaction.text,
        tool_count=len(defs),
        redaction_applied=len(redaction.patterns) > 0,
        redaction_patterns=list(redaction.patterns),
        server_name=server.name,
        server_version=server.version,
        protocol_version=server.protocol_version,
        catalog_ttl_ms=cache.ttl_ms if cache else None,
        catalog_cache_scope=cache.cache_scope if cache else None,
    )


def _to_tool_def(tool: Any) -> dict[str, Any] | None:
    """Project one tool onto the ToolDef wire keys; entries without a name are dropped."""
    if tool is None or isinstance(tool, (str, int, float, bool)):
        return None
    name = get_field(tool, "name")
    if not isinstance(name, str) or not name:
        return None
    out: dict[str, Any] = {"name": name}
    description = get_field(tool, "description")
    if isinstance(description, str):
        out["description"] = description
    for wire_key in ("inputSchema", "outputSchema", "annotations"):
        value = get_field(tool, wire_key)
        if value is not None:
            out[wire_key] = _plain(value)
    return out
