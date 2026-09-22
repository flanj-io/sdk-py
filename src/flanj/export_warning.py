"""Say something, once, the first time an OTLP export fails.

The OpenTelemetry SDK routes export errors to a logger nobody configured, so a
collector that is down - or an endpoint missing its ``/v1/logs`` path - is zero
records, zero output and a clean exit. The TypeScript SDK wraps its exporter for
the same reason and prints the same line (``export-failure-warning.ts``).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import Any

WarnFn = Callable[[str], None]


def export_failure_message(endpoint: str, detail: str) -> str:
    """The warning text - identical in shape to the TypeScript SDK's."""
    hint = ""
    if not endpoint.rstrip("/").endswith("/v1/logs"):
        hint = f" — the endpoint must include the OTLP logs path, e.g. {endpoint.rstrip('/')}/v1/logs"
    return (
        f"[flanj] OTLP log export to {endpoint} failed: {detail}{hint}. "
        f"Captured calls are being dropped; this warning is not repeated."
    )


def with_export_failure_warning(exporter: Any, endpoint: str, warn: WarnFn | None = None) -> Any:
    """Wrap an OTel log exporter so its FIRST failed export prints one line."""
    from opentelemetry.sdk._logs import export as _otel_export

    # Renamed upstream (logs are not a stable signal yet): current releases warn
    # on `LogExporter` and will remove it; older ones have only that name.
    base: Any = getattr(_otel_export, "LogRecordExporter", None) or _otel_export.LogExporter

    emit: WarnFn = warn or (lambda message: print(message, file=sys.stderr))

    class _WarningExporter(base):  # type: ignore[misc]
        def __init__(self) -> None:
            self._warned = False

        def export(self, batch: Sequence[Any]) -> Any:
            try:
                result = exporter.export(batch)
            except Exception as exc:
                self._warn(f"{type(exc).__name__}: {exc}")
                raise
            # By NAME, never by enum identity: opentelemetry 1.44 has the exporter
            # return `LogRecordExportResult.SUCCESS` while the older `LogExportResult`
            # class still exists beside it. Two Enum classes never compare equal, so
            # an identity comparison called every successful export a failure.
            if getattr(result, "name", None) != "SUCCESS":
                self._warn("the exporter reported FAILURE (is the collector running at that address?)")
            return result

        def _warn(self, detail: str) -> None:
            if self._warned:
                return
            self._warned = True
            try:
                emit(export_failure_message(endpoint, detail))
            except Exception:
                pass

        def shutdown(self) -> None:
            exporter.shutdown()

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            flush = getattr(exporter, "force_flush", None)
            return bool(flush(timeout_millis)) if callable(flush) else True

    return _WarningExporter()
