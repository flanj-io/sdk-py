"""MCP client capture - the whole of this SDK's v1 surface."""

from .assemble_call import assemble_mcp_call
from .assemble_snapshot import assemble_contract_snapshot
from .instrument import instrument_mcp_client
from .record import (
    build_contract_snapshot_attributes,
    build_mcp_call_attributes,
    emit_contract_snapshot,
    emit_mcp_call,
)
from .resolve_edge import UNKNOWN_MCP_SERVER, McpEdge, resolve_mcp_edge
from .types import (
    McpCallMeta,
    McpCapturedCall,
    McpContractSnapshot,
    McpServerIdentity,
    McpServerKind,
)

__all__ = [
    "instrument_mcp_client",
    "assemble_mcp_call",
    "assemble_contract_snapshot",
    "build_mcp_call_attributes",
    "build_contract_snapshot_attributes",
    "emit_mcp_call",
    "emit_contract_snapshot",
    "resolve_mcp_edge",
    "McpEdge",
    "UNKNOWN_MCP_SERVER",
    "McpCallMeta",
    "McpCapturedCall",
    "McpContractSnapshot",
    "McpServerIdentity",
    "McpServerKind",
]
