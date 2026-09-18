"""OTLP endpoint resolution: ``FLANJ_``/``OTEL_`` precedence and URL normalization.

Mirrors the TypeScript SDK's ``otlp-endpoint.ts`` so the same environment configures
both SDKs identically:

1. an explicit argument wins;
2. then ``FLANJ_OTLP_ENDPOINT`` (Flanj-specific, so it can differ from the app's own
   OTel export target);
3. then ``OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`` (already a full signal URL);
4. then ``OTEL_EXPORTER_OTLP_ENDPOINT`` (a base URL, so ``/v1/logs`` is appended).

A base URL is normalized to the logs path; a URL that already names a signal path is
left alone. Getting this wrong is silent - the exporter POSTs to a 404 and the
collector simply never sees a record.
"""

from __future__ import annotations

import os

DEFAULT_ENDPOINT = "http://localhost:4318/v1/logs"
LOGS_PATH = "/v1/logs"


def resolve_otlp_endpoint(endpoint: str | None = None) -> str:
    if endpoint:
        return _normalize(endpoint, already_signal=True)
    flanj = os.environ.get("FLANJ_OTLP_ENDPOINT")
    if flanj:
        return _normalize(flanj, already_signal=True)
    logs = os.environ.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
    if logs:
        return logs.rstrip("/") if logs.endswith("/") else logs
    base = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if base:
        return base.rstrip("/") + LOGS_PATH
    return DEFAULT_ENDPOINT


def _normalize(url: str, already_signal: bool) -> str:
    """Append ``/v1/logs`` to a base URL; leave a signal URL alone."""
    trimmed = url.rstrip("/")
    if trimmed.endswith(LOGS_PATH):
        return trimmed
    # A URL naming some other signal is the caller's explicit choice; only a bare
    # base (no path, or just `/`) gets the logs path appended.
    from urllib.parse import urlsplit

    try:
        path = urlsplit(trimmed).path
    except ValueError:
        return trimmed
    if path in ("", "/"):
        return trimmed + LOGS_PATH
    return trimmed
