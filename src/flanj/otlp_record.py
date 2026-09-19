"""Map a redacted call to the frozen ``flanj.*`` OTLP log-record attribute convention.

CONTRACTS section 2. Only redacted values are ever placed here; there is no code
path from a raw body to these attributes.

Attribute VALUES that are JSON documents (headers, patterns, fields) are serialized
the way every other Flanj SDK serializes them: compact separators and non-ASCII
written raw, i.e. byte-identical to JavaScript's ``JSON.stringify``. The collector
compares these strings; a stray space would be a wire difference.
"""

from __future__ import annotations

import json
from typing import Any

from .captured_call import CapturedCall
from .version import CAPTURE_VERSION

#: OTLP severity number for INFO.
SEVERITY_INFO = 9
SEVERITY_TEXT_INFO = "INFO"

LogAttributes = dict[str, Any]


def wire_json(value: Any) -> str:
    """Serialize exactly as JavaScript's ``JSON.stringify`` does."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_log_attributes(call: CapturedCall) -> LogAttributes:
    attrs: LogAttributes = {
        "flanj.capture.version": CAPTURE_VERSION,
        "flanj.record.type": "call",
        "flanj.direction": call.direction,
        "flanj.peer.host": call.peer_host,
        "flanj.edge.class": call.edge_class,
        "flanj.capture.bodies": call.capture_bodies,
        "flanj.http.method": call.method,
        "flanj.http.route": call.route,
        "flanj.http.target": call.target,
        "flanj.http.url.full": call.url_full,
        "flanj.http.status_code": call.status_code,
        "flanj.http.request.body": call.request_body,
        "flanj.http.request.body.truncated": call.request_body_truncated,
        "flanj.http.request.headers": wire_json(call.request_headers),
        "flanj.http.response.body": call.response_body,
        "flanj.http.response.body.truncated": call.response_body_truncated,
        "flanj.http.response.headers": wire_json(call.response_headers),
        "flanj.http.duration_ms": call.duration_ms,
        "flanj.redaction.applied": call.redaction_applied,
        "flanj.redaction.patterns": wire_json(call.redaction_patterns),
        "flanj.redaction.spec_aware": call.redaction_spec_aware,
    }

    if call.redaction_fields:
        # Optional attr (omitted when empty, like content_type/corr.*): whole-value
        # body redactions with the originals' captured properties - drift's evidence
        # for validating redacted fields (CONTRACTS section 2/6).
        attrs["flanj.redaction.fields"] = wire_json(call.redaction_fields)
    if call.peer_addr:
        attrs["flanj.peer.addr"] = call.peer_addr
    if call.request_content_type:
        attrs["flanj.http.request.content_type"] = call.request_content_type
    if call.response_content_type:
        attrs["flanj.http.response.content_type"] = call.response_content_type
    if call.correlation.request_id:
        attrs["flanj.corr.request_id"] = call.correlation.request_id
    if call.correlation.idempotency_key:
        attrs["flanj.corr.idempotency_key"] = call.correlation.idempotency_key
    if call.correlation.trace_id:
        attrs["flanj.corr.trace_id"] = call.correlation.trace_id
    if call.correlation.span_id:
        attrs["flanj.corr.span_id"] = call.correlation.span_id

    return attrs
