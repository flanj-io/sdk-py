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
import sys
from dataclasses import dataclass, field
from typing import Any

from .config import DEFAULT_BODY_CAP_BYTES
from .export_warning import with_export_failure_warning
from .otlp_endpoint import resolve_otlp_endpoint
from .runtime import assert_supported_python
from .version import SCOPE_NAME, __version__

#: Default shared with the TypeScript SDK's ``start()`` (CONTRACTS section 2,
#: "Resource attributes"; the consumer-branded default it replaced is retired
#: 2026-09-19).
DEFAULT_SERVICE_NAME = "flanj-sdk"


@dataclass
class FlanjHandle:
    """What ``start()`` returns: the provider, its logger, and how to stop it."""

    logger_provider: Any
    logger: Any
    #: The resolved ``service.name`` this handle's records carry.
    service_name: str
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
        """``instrument_mcp_client`` with this handle's logger and cap."""
        from .mcp import instrument_mcp_client

        options.setdefault("logger", self.logger)
        options.setdefault("body_cap_bytes", self.body_cap_bytes)
        return instrument_mcp_client(session, **options)


def start(
    service_name: str | None = None,
    otlp_endpoint: str | None = None,
    body_cap_bytes: int | None = None,
    simple_processor: bool = False,
    processor: Any = None,
) -> FlanjHandle:
    """Build the OTLP export path and patch the MCP transport openers.

    :param service_name: ``service.name``. Else ``OTEL_SERVICE_NAME``; else the
        app's own name (see :func:`_app_name`); else ``"flanj-sdk"``.
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

    resolved_service = (
        service_name
        or os.environ.get("OTEL_SERVICE_NAME")
        or _app_name(sys.modules.get("__main__"))
        or DEFAULT_SERVICE_NAME
    )
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
        service_name=resolved_service,
        endpoint=endpoint,
        body_cap_bytes=cap if cap is not None else DEFAULT_BODY_CAP_BYTES,
    )


def _app_name(main: object | None) -> str | None:
    """The running script/module's own name, read from ``sys.modules["__main__"]``.

    CONTRACTS section 2 ("Resource attributes"), Python column. Computed fresh on
    every call - never cached at import time, so it reflects whatever ``__main__``
    is by the time ``start()`` actually runs. Reads no file.

    Order: the entry module's dotted ``__spec__.name`` (``python -m pkg.mod``),
    with one trailing ``.__main__`` removed (``python -m myapp`` -> ``myapp``;
    ``python -m pkg.cli`` -> ``pkg.cli``); else the ``__file__`` basename with one
    trailing ``.py`` removed (``python path/app.py`` -> ``app``; a console-script
    launcher such as ``/venv/bin/gunicorn`` -> ``gunicorn``, as Datadog's does).
    A resolved name of ``"__main__"`` (a directory or zip run as a script) is no
    name at all, at either step: it falls through to the next rule, and if that
    also yields nothing, to None - the caller's cue to use ``DEFAULT_SERVICE_NAME``.
    A REPL, ``python -c``, or an embedded interpreter has neither a spec nor a
    ``__file__`` and also yields None.
    """
    if main is None:
        return None

    spec = getattr(main, "__spec__", None)
    spec_name = getattr(spec, "name", None) if spec is not None else None
    if isinstance(spec_name, str) and spec_name:
        name = spec_name[: -len(".__main__")] if spec_name.endswith(".__main__") else spec_name
        if name and name != "__main__":
            return name

    file = getattr(main, "__file__", None)
    if isinstance(file, str) and file:
        base = os.path.basename(file)
        if base.endswith(".py"):
            base = base[: -len(".py")]
        if base and base != "__main__":
            return base

    return None


def _env_int(key: str) -> int | None:
    raw = os.environ.get(key)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
