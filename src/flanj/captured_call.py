"""The redacted, transport-agnostic shape one completed call is handed over as.

It NEVER contains a raw body: the raw capture buffer is redacted and dropped
before a :class:`CapturedCall` is constructed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .redaction import PatternId


@dataclass
class Correlation:
    request_id: str | None = None
    idempotency_key: str | None = None
    trace_id: str | None = None
    span_id: str | None = None


@dataclass
class CapturedCall:
    direction: str  # 'client' | 'server'
    #: The OTHER end's host[:port] - egress: destination. The edge key.
    peer_host: str
    #: ``external`` | ``internal`` | ``local-process`` (CONTRACTS section 2).
    edge_class: str
    #: True when bodies are present (external edge); False when metadata-only.
    capture_bodies: bool
    method: str
    route: str
    target: str
    url_full: str
    status_code: int
    request_body: str  # redacted
    request_body_truncated: bool
    request_headers: dict[str, str]  # redacted + allowlisted
    response_body: str  # redacted
    response_body_truncated: bool
    response_headers: dict[str, str]  # redacted + allowlisted
    duration_ms: int
    redaction_applied: bool
    redaction_patterns: list[PatternId]
    redaction_spec_aware: bool
    #: Whole-value body redactions with captured properties; often empty. Each entry
    #: is the floor's field record with a ``part`` key prepended.
    redaction_fields: list[dict[str, Any]] = field(default_factory=list)
    correlation: Correlation = field(default_factory=Correlation)
    request_content_type: str | None = None
    response_content_type: str | None = None
    #: The peer's socket address (IP) when known. Transport detail for display and
    #: debugging; NEVER an identity or edge key.
    peer_addr: str | None = None
