"""MCP capture types (v0.5 spec section 4.B)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..captured_call import CapturedCall
from ..redaction import PatternId

#: How the MCP server is reached, as far as the CLIENT can tell. The SDK
#: instruments the client session, never a transport - this is derived from the
#: session's own transport reference / config, not from sniffing.
McpServerKind = str  # 'streamable-http' | 'stdio' | 'unknown'

EdgeClass = str  # 'external' | 'internal' | 'local-process' | 'unknown'


@dataclass
class McpServerIdentity:
    """Server identity (all optional - feature-detected).

    Protocol revision 2026-07-28 removed the ``initialize`` handshake, so the
    client-side accessors that used to carry this are empty against a current
    server. The authoritative source is now the ``_meta`` of every result
    (``io.modelcontextprotocol/serverInfo``); the handshake accessors survive only
    as a fallback for servers still on an older revision.
    """

    name: str | None = None
    version: str | None = None
    protocol_version: str | None = None
    #: ``capabilities.tools.listChanged`` when the session exposes capabilities.
    list_changed: bool | None = None


@dataclass
class McpCallMeta:
    """MCP-specific metadata attached to a captured tool call."""

    tool_name: str
    #: The MCP result's ``isError`` flag (also true when the call raised).
    is_error: bool
    server_kind: McpServerKind
    server_name: str | None = None
    server_version: str | None = None
    protocol_version: str | None = None
    #: ``Mcp-Session-Id`` when the transport exposes one. Protocol-level sessions
    #: were removed in revision 2026-07-28 along with the handshake, so this is
    #: permanently absent against a current server. The slot is kept - every reader
    #: treats it as optional - so a client still on the 2025-11-25 line keeps
    #: reporting what it has.
    session_id: str | None = None
    #: The result's ``resultType`` (revision 2026-07-28), verbatim: ``complete``,
    #: ``input_required``, or whatever a future revision adds. Absent on older
    #: servers, which must NOT be read as ``complete``.
    result_type: str | None = None
    #: Set when the result was a Tasks HANDLE rather than a payload. Such a record
    #: describes the envelope, never the tool's output, so nothing may validate or
    #: model response shape from it.
    task_id: str | None = None
    #: The JSON-RPC request id observed on the client's own outgoing message -
    #: CLIENT-GENERATED. It appears in the provider's logs only if they log it; it
    #: is never presented as a provider-issued id.
    client_request_id: str | None = None
    #: The JSON-RPC ``error.code`` when the ``tools/call`` REQUEST itself was
    #: rejected (``flanj.mcp.error.code``) - never for a result with ``isError``.
    error_code: int | None = None


@dataclass
class McpCapturedCall:
    """One captured MCP tool call on the SAME redacted shape as HTTP.

    The tool name rides the method/route slots (``tools/call`` + ``/<tool>``),
    arguments are the request body, ``structuredContent`` (else ``content[]`` text)
    is the response body - all floor-redacted at source. ``status_code`` is always 0
    (MCP has none; ``mcp.is_error`` carries the outcome).
    """

    call: CapturedCall
    mcp: McpCallMeta
    transport: str = "mcp"


@dataclass
class McpContractSnapshot:
    """One complete observed ``tools/list`` - the self-delivering contract snapshot.

    ``snapshot_json`` is the floor-REDACTED canonical JSON the collector's loader
    decodes: ``{"tools":[ToolDef...],"serverInfo"?,"protocolVersion"?,"capabilities"?}``
    with ToolDef wire keys ``name/description/inputSchema/outputSchema/annotations``.
    """

    integration: str
    peer_host: str
    edge_class: EdgeClass
    server_kind: McpServerKind
    snapshot_json: str
    tool_count: int
    redaction_applied: bool
    redaction_patterns: list[PatternId] = field(default_factory=list)
    server_name: str | None = None
    server_version: str | None = None
    protocol_version: str | None = None
    #: ``ttlMs`` / ``cacheScope`` from the ``tools/list`` result (revision
    #: 2026-07-28), when the server published them. Clients are now told to CACHE
    #: catalogs, so the list a snapshot records may legitimately be up to ``ttlMs``
    #: behind the server - a reader that presents a snapshot as live would be
    #: overstating it.
    catalog_ttl_ms: float | None = None
    catalog_cache_scope: str | None = None
    #: stdio only: ``flanj.mcp.server.command`` (see :mod:`flanj.mcp.launch`).
    server_command: str | None = None
