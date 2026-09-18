"""MCP edge identity (v0.5 spec section 4.B "Edge classification")."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from ..classify_host import classify_host
from .transports import TransportTag
from .types import EdgeClass, McpServerKind

#: Fallback edge key when a server has not surfaced a serverInfo.name yet.
UNKNOWN_MCP_SERVER = "unknown-mcp-server"

#: The edge class of a server whose transport the SDK never saw, so it cannot tell
#: a remote server from a local one. Bodies are NOT captured (it might be
#: internal), and the SDK says so once. See CONTRACTS section 2.
EDGE_CLASS_UNKNOWN = "unknown"


@dataclass
class McpEdge:
    #: The edge key: a URL-addressed server -> its host[:port]; stdio -> serverInfo.name.
    peer_host: str
    #: `external` | `internal` for a URL-addressed server (the shared heuristic);
    #: `local-process` for a server the app launched over stdio (bodies captured - it
    #: usually fronts someone else's API); `unknown` when nothing said which.
    edge_class: EdgeClass
    server_kind: McpServerKind


def resolve_mcp_edge(
    endpoint: str | None = None,
    server_kind: McpServerKind | None = None,
    transport: Any = None,
    server_name: str | None = None,
    tag: TransportTag | None = None,
) -> McpEdge:
    """Resolve the MCP edge from what is actually known. Never raises.

    In order: explicit config (``endpoint`` / ``server_kind``); the tag the
    transport opener left on the session's streams; a transport object exposing
    its URL (hand-rolled clients, and the TypeScript SDK's only path). When none of
    them says anything, the edge is ``unknown`` - never guessed. The TypeScript SDK
    falls back to stdio here, but there a missing URL really does mean stdio; in
    Python it only means the SDK was not loaded before the transport opened.
    """
    url = endpoint
    kind = server_kind
    if tag is not None:
        if url is None:
            url = tag.url
        if kind is None:
            kind = tag.kind
    if url is None:
        url = _transport_url(transport)
    if kind is None and url is not None:
        kind = "streamable-http"

    if kind == "streamable-http":
        host = _safe_host(url) if url is not None else None
        if host is None:
            # Declared HTTP but no resolvable URL: key by name, still HTTP-classified.
            host = server_name if server_name is not None else UNKNOWN_MCP_SERVER
        return McpEdge(peer_host=host, edge_class=classify_host(host), server_kind="streamable-http")
    if kind == "stdio":
        return McpEdge(
            peer_host=server_name if server_name is not None else UNKNOWN_MCP_SERVER,
            edge_class="local-process",
            server_kind="stdio",
        )
    return McpEdge(
        peer_host=server_name if server_name is not None else UNKNOWN_MCP_SERVER,
        edge_class=EDGE_CLASS_UNKNOWN,
        server_kind="unknown",
    )


def _transport_url(transport: Any) -> str | None:
    """A transport's endpoint URL when it exposes one."""
    if transport is None:
        return None
    for key in ("url", "_url", "endpoint"):
        try:
            value = getattr(transport, key, None)
        except Exception:
            continue  # hostile descriptor - read-only feature detection never raises
        if isinstance(value, str) and value:
            return value
        if value is not None and type(value).__name__ in ("URL", "Url", "AnyUrl", "AnyHttpUrl"):
            text = str(value)
            if text:
                return text
    return None


def _safe_host(url: str) -> str | None:
    try:
        netloc = urlsplit(url).netloc
    except ValueError:
        return None
    # `netloc` carries userinfo when present; the edge key is host[:port] only.
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    return netloc or None
