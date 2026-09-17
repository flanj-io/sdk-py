"""Redact at source and assemble a :class:`CapturedCall`.

Bodies are handed in as ALREADY-DECODED strings; this function redacts them at
source. Raw buffers must be dropped by the caller the moment this returns.

Bodies are redacted-and-kept ONLY when ``capture_bodies`` is true (external edge)
AND the content-type is captureable. Internal edges keep NO body at all. Target/URL
are always redacted (they are metadata, and the floor covers everything captured).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .captured_call import CapturedCall, Correlation
from .config import DEFAULT_BODY_CAP_BYTES, DEFAULT_CAPTURE_CONTENT_TYPES, is_captureable_content_type
from .redaction import (
    DEFAULT_HEADER_ALLOWLIST,
    REPORT_ORDER,
    PatternId,
    RedactedField,
    redact_detailed,
    redact_headers,
)


def assemble_captured_call(
    *,
    integration: str,
    direction: str,
    peer_host: str,
    edge_class: str,
    capture_bodies: bool,
    method: str,
    protocol: str,
    host: str,
    path: str,
    status_code: int,
    req_body_raw: str,
    req_body_truncated: bool,
    res_body_raw: str,
    res_body_truncated: bool,
    request_headers: Mapping[str, Any],
    response_headers: Mapping[str, Any],
    correlation: Correlation,
    duration_ms: int,
    req_content_type: str | None = None,
    res_content_type: str | None = None,
    peer_addr: str | None = None,
    capture_content_types: Sequence[str] = DEFAULT_CAPTURE_CONTENT_TYPES,
    header_allowlist: Sequence[str] = DEFAULT_HEADER_ALLOWLIST,
    body_cap_bytes: int = DEFAULT_BODY_CAP_BYTES,
) -> CapturedCall:
    capture_req = capture_bodies and is_captureable_content_type(req_content_type, capture_content_types)
    capture_res = capture_bodies and is_captureable_content_type(res_content_type, capture_content_types)

    empty: tuple[str, list[PatternId], list[RedactedField]] = ("", [], [])
    req = redact_detailed(req_body_raw) if capture_req else empty
    res = redact_detailed(res_body_raw) if capture_res else empty
    target = redact_detailed(path)
    url = redact_detailed(f"{protocol}//{host}{path}")

    fired = set(req[1]) | set(res[1]) | set(target.patterns) | set(url.patterns)
    patterns = [p for p in REPORT_ORDER if p in fired]

    # Whole-value body redactions, with the original values' captured properties
    # (already sorted by path per part; request precedes response). Target/URL
    # redactions carry no fields - specs do not address redacted URL text.
    redaction_fields: list[dict[str, Any]] = []
    for part, source in (("request", req[2]), ("response", res[2])):
        for f in source:
            entry: dict[str, Any] = {"part": part}
            entry.update(f)
            redaction_fields.append(entry)

    return CapturedCall(
        integration=integration,
        direction=direction,
        peer_host=peer_host,
        peer_addr=peer_addr,
        edge_class=edge_class,
        capture_bodies=capture_bodies,
        method=method,
        route=target.text,
        target=target.text,
        url_full=url.text,
        status_code=status_code,
        request_content_type=req_content_type,
        request_body=req[0],
        request_body_truncated=req_body_truncated if capture_req else False,
        request_headers=redact_headers(request_headers, header_allowlist),
        response_content_type=res_content_type,
        response_body=res[0],
        response_body_truncated=res_body_truncated if capture_res else False,
        response_headers=redact_headers(response_headers, header_allowlist),
        correlation=correlation,
        duration_ms=duration_ms,
        redaction_applied=len(patterns) > 0,
        redaction_patterns=patterns,
        redaction_spec_aware=False,
        redaction_fields=redaction_fields,
    )
