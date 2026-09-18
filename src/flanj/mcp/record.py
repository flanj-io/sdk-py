"""Map MCP capture onto the ``flanj.*`` OTLP convention (CONTRACTS section 2)."""

from __future__ import annotations

from typing import Any

from ..otlp_record import SEVERITY_TEXT_INFO, LogAttributes, build_log_attributes, wire_json
from ..version import CAPTURE_VERSION
from .types import McpCapturedCall, McpContractSnapshot


def build_mcp_call_attributes(captured: McpCapturedCall) -> LogAttributes:
    """The HTTP call mapping plus the additive ``flanj.transport`` / ``flanj.mcp.*``
    attributes, minus ``flanj.http.status_code`` (MCP has none - ``flanj.mcp.is_error``
    carries the outcome).

    The JSON-RPC id rides ``flanj.corr.client_request_id``, a slot whose name says
    what it is: CLIENT-generated, never a provider-issued id.
    """
    attrs = build_log_attributes(captured.call)
    attrs.pop("flanj.http.status_code", None)

    mcp = captured.mcp
    attrs["flanj.transport"] = "mcp"
    attrs["flanj.mcp.tool.name"] = mcp.tool_name
    attrs["flanj.mcp.is_error"] = mcp.is_error
    if mcp.server_name is not None:
        attrs["flanj.mcp.server.name"] = mcp.server_name
    if mcp.server_version is not None:
        attrs["flanj.mcp.server.version"] = mcp.server_version
    if mcp.protocol_version is not None:
        attrs["flanj.mcp.protocol.version"] = mcp.protocol_version
    if mcp.session_id is not None:
        attrs["flanj.mcp.session.id"] = mcp.session_id
    # Revision 2026-07-28. Omitted (never defaulted) when the server did not send
    # them: absent `resultType` means "an older server", not `complete`.
    if mcp.result_type is not None:
        attrs["flanj.mcp.result.type"] = mcp.result_type
    if mcp.task_id is not None:
        attrs["flanj.mcp.task.id"] = mcp.task_id
    if mcp.client_request_id is not None:
        attrs["flanj.corr.client_request_id"] = mcp.client_request_id
    if mcp.error_code is not None:
        attrs["flanj.mcp.error.code"] = mcp.error_code
    return attrs


def build_contract_snapshot_attributes(snap: McpContractSnapshot) -> LogAttributes:
    """One record per COMPLETE observed ``tools/list``; the observation timestamp is
    the log record's own timestamp.
    """
    attrs: LogAttributes = {
        "flanj.capture.version": CAPTURE_VERSION,
        "flanj.record.type": "contract_snapshot",
        "flanj.transport": "mcp",
        "flanj.direction": "client",
        "flanj.peer.host": snap.peer_host,
        "flanj.edge.class": snap.edge_class,
        "flanj.integration": snap.integration,
        "flanj.mcp.contract_snapshot": snap.snapshot_json,
        "flanj.mcp.tool.count": snap.tool_count,
        "flanj.redaction.applied": snap.redaction_applied,
        "flanj.redaction.patterns": wire_json(snap.redaction_patterns),
    }
    if snap.server_name is not None:
        attrs["flanj.mcp.server.name"] = snap.server_name
    if snap.server_version is not None:
        attrs["flanj.mcp.server.version"] = snap.server_version
    if snap.protocol_version is not None:
        attrs["flanj.mcp.protocol.version"] = snap.protocol_version
    # Revision 2026-07-28: clients are told to CACHE catalogs, so a snapshot may
    # legitimately be up to `ttlMs` behind the server.
    if snap.catalog_ttl_ms is not None:
        attrs["flanj.mcp.catalog.ttl_ms"] = snap.catalog_ttl_ms
    if snap.catalog_cache_scope is not None:
        attrs["flanj.mcp.catalog.cache_scope"] = snap.catalog_cache_scope
    if snap.server_command is not None:
        attrs["flanj.mcp.server.command"] = snap.server_command
    return attrs


def emit_mcp_call(logger: Any, captured: McpCapturedCall) -> None:
    """Emit one OTLP log record for a completed MCP tool call.

    The record body is empty; all data lives in the ``flanj.*`` attributes.
    """
    _emit(logger, build_mcp_call_attributes(captured))


def emit_contract_snapshot(logger: Any, snap: McpContractSnapshot) -> None:
    """Emit one OTLP log record for a complete observed ``tools/list``."""
    _emit(logger, build_contract_snapshot_attributes(snap))


def _emit(logger: Any, attributes: LogAttributes) -> None:
    """Emit one record, across both shapes of the OpenTelemetry logs API.

    Current versions take the fields as keyword arguments on ``Logger.emit``; older
    ones take a single ``LogRecord``. Which one is in the user's environment is not
    ours to choose - this SDK is a guest in an application that may already pin an
    OpenTelemetry version - so the shape is detected once, from the signature, rather
    than guessed or discovered through a ``TypeError`` that would also swallow real
    errors.
    """
    from opentelemetry._logs import SeverityNumber

    if _emit_takes_keywords(logger):
        logger.emit(
            severity_number=SeverityNumber.INFO,
            severity_text=SEVERITY_TEXT_INFO,
            body="",
            attributes=attributes,
        )
        return
    # Private by nature: this is the pre-keyword-argument shape of the API, and
    # there is no public name for it.
    from opentelemetry.sdk._logs._internal import LogRecord  # type: ignore[attr-defined]

    logger.emit(
        LogRecord(
            body="",
            severity_number=SeverityNumber.INFO,
            severity_text=SEVERITY_TEXT_INFO,
            attributes=attributes,
        )
    )


def _emit_takes_keywords(logger: Any) -> bool:
    import inspect

    try:
        return "attributes" in inspect.signature(logger.emit).parameters
    except (TypeError, ValueError):
        return False
