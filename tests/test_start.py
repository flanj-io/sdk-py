"""`start()`, its handle, the export-failure warning, flush on exit and the zero-code entry.

Each mirrors a TypeScript SDK module (`index.ts` start, `export-failure-warning.ts`,
`flush-on-exit.ts`, `register.ts`); the only intended difference between the SDKs
is HTTP capture.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from flanj import flush_on_exit, start
from flanj.export_warning import export_failure_message, with_export_failure_warning

SRC = Path(__file__).resolve().parent.parent / "src"


class _Recorder:
    def __init__(self) -> None:
        self.records: list[Any] = []

    def emit(self, record: Any) -> None:  # LogRecordProcessor API
        self.records.append(record)

    on_emit = emit

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def test_start_reads_the_same_environment_as_the_typescript_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLANJ_INTEGRATION_ID", "acme-tools")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "my-agent")
    monkeypatch.setenv("FLANJ_OTLP_ENDPOINT", "http://collector:4318")
    monkeypatch.setenv("FLANJ_BODY_CAP_BYTES", "4096")
    handle = start(processor=_Recorder())
    try:
        assert handle.integration == "acme-tools"
        assert handle.endpoint == "http://collector:4318/v1/logs"
        assert handle.body_cap_bytes == 4096
        resource = dict(handle.logger_provider.resource.attributes)
        assert resource["service.name"] == "my-agent"
    finally:
        handle.shutdown()


def test_start_defaults_match_the_typescript_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("FLANJ_INTEGRATION_ID", "OTEL_SERVICE_NAME", "FLANJ_OTLP_ENDPOINT", "FLANJ_BODY_CAP_BYTES",
                "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"):
        monkeypatch.delenv(key, raising=False)
    handle = start(processor=_Recorder())
    try:
        assert handle.integration is None, "unset means one integration per server, not a shared id"
        assert handle.endpoint == "http://localhost:4318/v1/logs"
        assert handle.body_cap_bytes == 16384
        assert dict(handle.logger_provider.resource.attributes)["service.name"] == "flanj-consumer"
    finally:
        handle.shutdown()


def test_shutdown_is_idempotent() -> None:
    handle = start(processor=_Recorder())
    handle.shutdown()
    handle.shutdown()


def test_the_first_export_failure_warns_once_and_names_the_fix() -> None:
    from opentelemetry.sdk._logs.export import LogExportResult

    class Failing:
        def export(self, batch: Any) -> Any:
            return LogExportResult.FAILURE

        def shutdown(self) -> None:
            pass

    lines: list[str] = []
    exporter = with_export_failure_warning(Failing(), "http://collector:4318", warn=lines.append)
    exporter.export([])
    exporter.export([])
    assert len(lines) == 1, "the warning must not repeat"
    assert "http://collector:4318" in lines[0]
    assert "/v1/logs" in lines[0], "a base URL gets the logs-path hint"
    assert "Captured calls are being dropped" in lines[0]


def test_a_successful_export_says_nothing() -> None:
    from opentelemetry.sdk._logs.export import LogExportResult

    class Ok:
        def export(self, batch: Any) -> Any:
            return LogExportResult.SUCCESS

        def shutdown(self) -> None:
            pass

    lines: list[str] = []
    with_export_failure_warning(Ok(), "http://c:4318/v1/logs", warn=lines.append).export([])
    assert lines == []
    message = export_failure_message("http://c:4318/v1/logs", "x")
    assert "e.g." not in message, "no hint when the path is right"


def test_a_signal_flushes_first_then_behaves_exactly_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Handle:
        def flush(self, timeout_millis: int = 0) -> bool:
            calls.append("flush")
            return True

        def shutdown(self) -> None:
            calls.append("shutdown")

    registered: list[Any] = []
    monkeypatch.setattr("atexit.register", lambda fn, *a: registered.append((fn, a)))

    def previous(signum: int, frame: Any) -> None:
        calls.append("previous")

    original = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, previous)
    try:
        flush_on_exit(Handle())
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    finally:
        signal.signal(signal.SIGTERM, original)
    assert calls == ["shutdown", "previous"], "flush first, then the app's own handler - never instead"
    assert registered, "the normal-exit flush was not registered"


def _run_register(env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(SRC), "FLANJ_OTLP_ENDPOINT": "http://127.0.0.1:9/v1/logs"}
    env.pop("FLANJ_QUIET", None)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", "import flanj.register; import mcp.client.session as s; "
         "print('patched' if '__flanj_class_patched__' in vars(s.ClientSession) else 'not patched')"],
        capture_output=True, text=True, env=env, timeout=60, check=True,
    )


def test_the_zero_code_entry_starts_capture_and_says_so_once() -> None:
    result = _run_register({})
    assert result.stdout.strip() == "patched", "import flanj.register did not auto-instrument MCP"
    assert result.stderr.count("[flanj] flanj ") == 1
    assert "capturing MCP client calls" in result.stderr
    assert "FLANJ_QUIET=1" in result.stderr


def test_the_startup_line_can_be_silenced() -> None:
    result = _run_register({"FLANJ_QUIET": "1"})
    assert "[flanj] flanj " not in result.stderr
