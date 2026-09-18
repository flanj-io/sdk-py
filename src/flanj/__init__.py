"""Flanj SDK for Python - **Early: MCP client capture only**.

Out-of-band capture of MCP ``tools/call`` and ``tools/list`` traffic, redacted at
source, exported as OTLP log records to a collector you run. Raw bodies never leave
the process: the floor redacts before anything is attached or emitted.

What this SDK does NOT do, deliberately: HTTP request/response body capture. Python
has no ``node:http`` choke point to patch the way the TypeScript SDK does, and the
audience this is built for - agent and MCP-client applications - has MCP traffic to
watch, not a REST integration. MCP-only is a complete product for that shape, not a
partial SDK.

Quick start::

    from mcp import ClientSession
    from flanj import instrument_mcp_client, otlp_logger

    logger = otlp_logger(endpoint="http://localhost:4318/v1/logs", service_name="my-agent")
    session = ClientSession(read_stream, write_stream)
    instrument_mcp_client(session, integration="acme-tools", logger=logger)
    # use `session` exactly as before - nothing about its behaviour changes.

Requires Python >= 3.10 (see :mod:`flanj.runtime` for why, and for the three places
that floor is stated).

**Why the exports below are lazy (PEP 562).** Importing them eagerly would pull
``asyncio`` and the whole OpenTelemetry SDK into the process of anyone who imports
any part of this package - including someone who wanted only
:mod:`flanj.redaction`, whose defining property is that it has no I/O capability in
its module graph at all. Python initializes a parent package before its submodule,
so an eager ``__init__`` would put sockets and TLS behind ``import
flanj.redaction`` and make that property untestable. It is checked, in
``tests/redaction/test_module_graph.py``, and this is what keeps it true.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .version import CAPTURE_VERSION, __version__

if TYPE_CHECKING:  # type checkers only; at runtime these resolve via __getattr__
    from .mcp import (
        McpCapturedCall,
        McpContractSnapshot,
        build_contract_snapshot_attributes,
        build_mcp_call_attributes,
        instrument_mcp_client,
        resolve_mcp_edge,
    )
    from .otlp import otlp_logger
    from .otlp_endpoint import resolve_otlp_endpoint
    from .runtime import SUPPORTED_PYTHON, SUPPORTED_PYTHON_SPECIFIER, assert_supported_python

#: Public name -> the submodule that defines it.
_EXPORTS = {
    "instrument_mcp_client": "flanj.mcp",
    "resolve_mcp_edge": "flanj.mcp",
    "build_mcp_call_attributes": "flanj.mcp",
    "build_contract_snapshot_attributes": "flanj.mcp",
    "McpCapturedCall": "flanj.mcp",
    "McpContractSnapshot": "flanj.mcp",
    "otlp_logger": "flanj.otlp",
    "resolve_otlp_endpoint": "flanj.otlp_endpoint",
    "assert_supported_python": "flanj.runtime",
    "SUPPORTED_PYTHON": "flanj.runtime",
    "SUPPORTED_PYTHON_SPECIFIER": "flanj.runtime",
}

__all__ = [*sorted(_EXPORTS), "CAPTURE_VERSION", "__version__"]


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module_name), name)
    globals()[name] = value  # resolve once; later lookups skip __getattr__
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
