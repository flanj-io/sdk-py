"""``start()`` - the OTLP pipeline, set up the way the collector expects.

The Python counterpart of the TypeScript SDK's ``start()``: same options (minus
the HTTP-capture ones, the one intended difference between the SDKs), same
environment variables, same defaults, and a handle with ``flush()`` and
``shutdown()``.

It also patches the MCP transport openers (:mod:`flanj.mcp.transports`) so that
every session opened afterwards can be placed on the right edge. That is why
``start()`` is called - or ``flanj.register`` imported - before any MCP
transport is opened.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .config import DEFAULT_BODY_CAP_BYTES
from .export_warning import with_export_failure_warning
from .otlp_endpoint import resolve_otlp_endpoint
from .runtime import assert_supported_python
from .version import SCOPE_NAME, __version__

#: Defaults shared with the TypeScript SDK's ``start()``.
DEFAULT_INTEGRATION = "unknown-integration"
DEFAULT_SERVICE_NAME = "flanj-consumer"


@dataclass
class FlanjHandle:
    """What ``start()`` returns: the provider, its logger, and how to stop it."""

    logger_provider: Any
    logger: Any
    #: The configured integration id, or None to derive one per MCP server.
    integration: str | None
    endpoint: str
    body_cap_bytes: int = DEFAULT_BODY_CAP_BYTES
    _shut_down: bool = field(default=False, repr=False)

    def flush(self, timeout_millis: int = 5000) -> bool:
        """Export everything captured so far. Bounded; returns False on timeout."""
        return bool(self.logger_provider.force_flush(timeout_millis))

    def shutdown(self) -> None:
        """Flush and stop the exporter. Idempotent."""
        if self._shut_down:
            return
        self._shut_down = True
        self.logger_provider.shutdown()

    def instrument(self, session: Any, **options: Any) -> Any:
        """``instrument_mcp_client`` with this handle's logger, integration and cap."""
        from .mcp import instrument_mcp_client

        options.setdefault("logger", self.logger)
        options.setdefault("integration", self.integration)
        options.setdefault("body_cap_bytes", self.body_cap_bytes)
        return instrument_mcp_client(session, **options)


def start(
    integration: str | None = None,
    service_name: str | None = None,
    otlp_endpoint: str | None = None,
    body_cap_bytes: int | None = None,
    simple_processor: bool = False,
    processor: Any = None,
) -> FlanjHandle:
    """Build the OTLP export path and patch the MCP transport openers.

    :param integration: ``flanj.integration`` for every instrumented session. Else
        ``FLANJ_INTEGRATION_ID``; else derived per MCP server from its edge key.
    :param service_name: ``service.name``. Else ``OTEL_SERVICE_NAME``; else
        ``flanj-consumer`` (the TypeScript SDK's default).
    :param otlp_endpoint: the collector's logs endpoint; see
        :func:`~flanj.otlp_endpoint.resolve_otlp_endpoint` for the precedence.
    :param body_cap_bytes: per-body cap. Else ``FLANJ_BODY_CAP_BYTES``; else 16 KiB.
    :param simple_processor: export each record synchronously instead of batching.
    :param processor: a ready-made ``LogRecordProcessor`` to use instead.
    """
    assert_supported_python()

    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, SimpleLogRecordProcessor
    from opentelemetry.sdk.resources import Resource

    from .mcp.transports import patch_transport_openers

    resolved_integration = integration or os.environ.get("FLANJ_INTEGRATION_ID") or None
    resolved_service = service_name or os.environ.get("OTEL_SERVICE_NAME") or DEFAULT_SERVICE_NAME
    endpoint = resolve_otlp_endpoint(otlp_endpoint)
    cap = body_cap_bytes if body_cap_bytes is not None else _env_int("FLANJ_BODY_CAP_BYTES")

    if processor is None:
        exporter = with_export_failure_warning(OTLPLogExporter(endpoint=endpoint), endpoint)
        processor = (
            SimpleLogRecordProcessor(exporter) if simple_processor else BatchLogRecordProcessor(exporter)
        )

    provider = LoggerProvider(
        resource=Resource.create({"service.name": resolved_service, "telemetry.sdk.name": SCOPE_NAME}),
    )
    provider.add_log_record_processor(processor)

    patch_transport_openers()

    return FlanjHandle(
        logger_provider=provider,
        logger=provider.get_logger(SCOPE_NAME, __version__),
        integration=resolved_integration,
        endpoint=endpoint,
        body_cap_bytes=cap if cap is not None else DEFAULT_BODY_CAP_BYTES,
    )


def _env_int(key: str) -> int | None:
    raw = os.environ.get(key)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
