"""Redact at source and assemble one MCP tool call.

Funnelled through the one shared assembler
(:func:`~flanj.assemble_call.assemble_captured_call`) so every floor rule - cap,
content-type gate, internal-edge metadata-only, redaction-then-drop, captured-value
props - applies identically::

    method = "tools/call" | route/target = "/<tool.name>"
    url    = "mcp://<peer.host>/<tool.name>" | status_code = 0 (none in MCP)

A stdio server (``local-process``) captures bodies like an external edge; only a
streamable-HTTP peer classified ``internal`` stays metadata-only.
"""

from __future__ import annotations

import json
from typing import Any

from ..assemble_call import assemble_captured_call
from ..captured_call import Correlation
from ..config import DEFAULT_BODY_CAP_BYTES, cap_text
from .result_meta import get_field, result_type_of, task_id_of, trace_context_from_meta
from .types import EdgeClass, McpCallMeta, McpCapturedCall, McpServerKind


def assemble_mcp_call(
    *,
    integration: str,
    peer_host: str,
    edge_class: EdgeClass,
    server_kind: McpServerKind,
    tool_name: str,
    args: Any,
    result: Any,
    is_error: bool,
    duration_ms: int,
    server_name: str | None = None,
    server_version: str | None = None,
    protocol_version: str | None = None,
    session_id: str | None = None,
    client_request_id: str | None = None,
    error_code: int | None = None,
    body_cap_bytes: int = DEFAULT_BODY_CAP_BYTES,
) -> McpCapturedCall:
    req_text, req_truncated = cap_text(_serialize(args), body_cap_bytes)
    if _is_task_envelope(result):
        res_text, res_truncated, res_content_type = "", False, None
    else:
        res_text, res_truncated, res_content_type = _response_body(result, body_cap_bytes)
    trace = trace_context_from_meta(result)

    call = assemble_captured_call(
        integration=integration,
        direction="client",
        peer_host=peer_host,
        edge_class=edge_class,
        # Bodies only where we know the server is not internal. An `unknown` edge
        # might be internal, so it is treated as one: fail closed.
        capture_bodies=edge_class not in ("internal", "unknown"),
        method="tools/call",
        protocol="mcp:",
        host=peer_host,
        path=f"/{tool_name}",
        status_code=0,
        req_content_type="application/json",
        res_content_type=res_content_type,
        req_body_raw=req_text,
        req_body_truncated=req_truncated,
        res_body_raw=res_text,
        res_body_truncated=res_truncated,
        request_headers={},
        response_headers={},
        # Trace context now has a documented `_meta` convention (revision
        # 2026-07-28). Before it, the MCP path carried NO trace id at all while the
        # HTTP path filled both slots.
        correlation=(
            Correlation(trace_id=trace.trace_id, span_id=trace.span_id) if trace else Correlation()
        ),
        duration_ms=duration_ms,
        body_cap_bytes=body_cap_bytes,
    )

    meta = McpCallMeta(
        tool_name=tool_name,
        is_error=is_error,
        server_kind=server_kind,
        server_name=server_name,
        server_version=server_version,
        protocol_version=protocol_version,
        session_id=session_id,
        client_request_id=client_request_id,
        error_code=error_code,
        result_type=result_type_of(result),
        task_id=task_id_of(result),
    )
    return McpCapturedCall(call=call, mcp=meta)


def _is_task_envelope(result: Any) -> bool:
    """A Tasks handle is an ENVELOPE, not a result.

    ``tools/call`` returned ``{task: {taskId, status, ...}}`` and the tool's real
    payload arrives later via ``tasks/get``, on a surface this SDK does not yet
    instrument. Capturing the envelope's fields as if they were the tool's response
    body is how a detector ends up modelling ``taskId``/``status``/``createdAt`` as
    the tool's output shape - so the body is dropped and ``mcp.task_id`` says why the
    record is empty.
    """
    return task_id_of(result) is not None


def _serialize(value: Any) -> str:
    if value is None:
        return ""
    try:
        return json.dumps(_plain(value), ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return ""


def _plain(value: Any) -> Any:
    """Plain-data view of a value that may be a pydantic model."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    dump_calls = (
        ("model_dump", {"by_alias": True, "exclude_none": True}),
        ("dict", {"by_alias": True}),
    )
    for attr, kwargs in dump_calls:
        fn = getattr(value, attr, None)
        if callable(fn):
            try:
                return _plain(fn(**kwargs))
            except Exception:
                continue
    return value


def _response_body(result: Any, cap: int) -> tuple[str, bool, str | None]:
    """Response body.

    ``structuredContent`` when present (JSON), else the ``content[]`` text items
    joined with newlines (text - the floor's text path still parses-then-traverses
    it when it IS JSON, so a PAN nested in stringified JSON is caught structurally,
    not by a regex).
    """
    if result is None or isinstance(result, (str, int, float, bool)):
        return "", False, None
    structured = get_field(result, "structuredContent")
    if structured is not None:
        text, truncated = cap_text(_serialize(structured), cap)
        return text, truncated, "application/json"
    content = get_field(result, "content")
    if isinstance(content, (list, tuple)):
        texts = []
        for item in content:
            if get_field(item, "type") == "text":
                value = get_field(item, "text")
                if isinstance(value, str):
                    texts.append(value)
        if texts:
            text, truncated = cap_text("\n".join(texts), cap)
            return text, truncated, "text/plain"
    return "", False, None
