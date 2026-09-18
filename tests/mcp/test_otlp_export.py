"""The EXPORT path, end to end through a real OpenTelemetry LoggerProvider.

Everything else in this suite asserts on the attribute map a builder returns, or on
the sink callbacks. Neither touches ``logger.emit`` - so until this file existed, the
one path the integration harness actually depends on was the one path nothing
exercised. An SDK whose records are perfect and never leave the process is not a
working SDK.
"""

from __future__ import annotations

from typing import Any

import pytest

from flanj.mcp import instrument_mcp_client

pytest.importorskip("opentelemetry.sdk._logs", reason="the OpenTelemetry SDK is a runtime dependency")

from opentelemetry.sdk._logs import LoggerProvider  # noqa: E402
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor  # noqa: E402

try:  # renamed in newer OpenTelemetry SDKs; logs are not a stable signal yet
    from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter as _InMemoryExporter
except ImportError:  # pragma: no cover - older SDKs
    from opentelemetry.sdk._logs.export import InMemoryLogExporter as _InMemoryExporter


class FakeSession:
    def __init__(self) -> None:
        self.transport = type("T", (), {"url": "http://mcp.acme.test/mcp"})()

    async def call_tool(self, name: str, arguments: Any = None, **kwargs: Any) -> Any:
        return {"structuredContent": {"amount": 1200, "card_number": "4111111111111111"}}

    async def list_tools(self, **kwargs: Any) -> Any:
        return {
            "tools": [{"name": "get_balance", "inputSchema": {"type": "object"}}],
            "nextCursor": None,
        }


@pytest.fixture()
def exported() -> tuple[Any, Any]:
    exporter = _InMemoryExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    return provider.get_logger("flanj", "0.1.0"), exporter


async def test_a_tool_call_reaches_the_exporter_as_a_flanj_record(exported: Any) -> None:
    logger, exporter = exported
    session = FakeSession()
    instrument_mcp_client(session, integration="acme-tools", logger=logger)

    await session.call_tool("get_balance", {"account_id": "acct_1"})

    records = exporter.get_finished_logs()
    assert len(records) == 1, "the call never reached the exporter"
    record = records[0].log_record
    attrs = dict(record.attributes or {})

    assert attrs["flanj.record.type"] == "call"
    assert attrs["flanj.transport"] == "mcp"
    assert attrs["flanj.mcp.tool.name"] == "get_balance"
    assert attrs["flanj.integration"] == "acme-tools"
    assert attrs["flanj.peer.host"] == "mcp.acme.test"
    assert attrs["flanj.edge.class"] == "external"
    assert "flanj.http.status_code" not in attrs
    assert record.severity_text == "INFO"
    assert record.body == ""

    # The whole point: what left the process is redacted.
    assert "4111111111111111" not in attrs["flanj.http.response.body"]
    assert "⟦REDACTED:PAN⟧" in attrs["flanj.http.response.body"]


async def test_a_tools_list_reaches_the_exporter_as_a_contract_snapshot(exported: Any) -> None:
    logger, exporter = exported
    session = FakeSession()
    instrument_mcp_client(session, integration="acme-tools", logger=logger)

    await session.list_tools()

    records = exporter.get_finished_logs()
    assert len(records) == 1
    attrs = dict(records[0].log_record.attributes or {})
    assert attrs["flanj.record.type"] == "contract_snapshot"
    assert attrs["flanj.mcp.tool.count"] == 1
    assert "get_balance" in attrs["flanj.mcp.contract_snapshot"]


async def test_every_attribute_value_is_an_otlp_scalar(exported: Any) -> None:
    """OTLP attribute values must be a scalar or a homogeneous sequence of scalars.

    A dict or a nested list is dropped by the exporter - silently, per-attribute - so
    the collector would receive a record that is simply missing a field. This is why
    headers, patterns and fields are serialized to JSON strings rather than passed as
    structures.
    """
    logger, exporter = exported
    session = FakeSession()
    instrument_mcp_client(session, integration="acme-tools", logger=logger)

    await session.call_tool("get_balance", {"account_id": "acct_1"})

    attrs = dict(exporter.get_finished_logs()[0].log_record.attributes or {})
    assert attrs, "all attributes were dropped"
    for key, value in attrs.items():
        assert isinstance(value, (str, bool, int, float)), (
            f"{key} is {type(value).__name__}; OTLP would drop it and the collector "
            f"would never see the field"
        )
