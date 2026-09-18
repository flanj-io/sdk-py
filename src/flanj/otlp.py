"""The OTLP logs export path - one logger, wired the way the collector expects.

This is a thin convenience over the OpenTelemetry SDK. An application that already
owns a ``LoggerProvider`` should pass its own logger to
:func:`~flanj.mcp.instrument.instrument_mcp_client` instead; this exists so the
quick start is three lines and so the endpoint precedence is applied consistently.
"""

from __future__ import annotations

from typing import Any

from .otlp_endpoint import resolve_otlp_endpoint
from .runtime import assert_supported_python
from .version import SCOPE_NAME, __version__


def otlp_logger(
    endpoint: str | None = None,
    service_name: str | None = None,
    provider: Any = None,
) -> Any:
    """Build (or reuse) a logger that exports ``flanj.*`` records over OTLP/HTTP.

    :param endpoint: the collector's logs endpoint. Resolution order is documented
        in :func:`~flanj.otlp_endpoint.resolve_otlp_endpoint`.
    :param service_name: ``service.name`` on the exported resource. Falls back to
        the usual ``OTEL_SERVICE_NAME`` handling of the OpenTelemetry SDK.
    :param provider: an existing ``LoggerProvider`` to attach the exporter to,
        instead of creating one.
    """
    assert_supported_python()

    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import Resource

    if provider is None:
        attributes = {"telemetry.sdk.name": SCOPE_NAME}
        if service_name:
            attributes["service.name"] = service_name
        provider = LoggerProvider(resource=Resource.create(attributes))
        provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=resolve_otlp_endpoint(endpoint)))
        )
    return provider.get_logger(SCOPE_NAME, __version__)
