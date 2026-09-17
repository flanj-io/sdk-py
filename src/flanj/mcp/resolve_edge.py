"""MCP edge identity (v0.5 spec section 4.B "Edge classification")."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from ..classify_host import classify_host
from .types import EdgeClass, McpServerKind

#: Fallback edge key when a stdio server has not surfaced a serverInfo.name yet.
UNKNOWN_MCP_SERVER = "unknown-mcp-server"


@dataclass
class McpEdge:
    #: The edge key: streamable-HTTP -> endpoint URL host[:port]; stdio -> serverInfo.name.
    peer_host: str
    #: streamable-HTTP peers go through the existing external/internal heuristic;
    #: stdio servers are the class ``local-process`` (a local MCP process is usually a
    #: thin wrapper over an external API - captured, never surfaced as an internal
    #: HTTP edge).
    edge_class: EdgeClass
    server_kind: McpServerKind


def resolve_mcp_edge(
    endpoint: str | None = None,
    server_kind: McpServerKind | None = None,
    transport: Any = None,
    server_name: str | None = None,
) -> McpEdge:
    """Resolve the MCP edge from what the CLIENT exposes.

    An explicit endpoint/kind from config, else the transport's own ``url``
    attribute (streamable HTTP), else stdio. Read-only feature detection - never
    raises.
    """
    url = endpoint if endpoint is not None else _transport_url(transport)
    kind = server_kind if server_kind is not None else ("streamable-http" if url is not None else "stdio")

    if kind == "streamable-http" and url is not None:
        host = _safe_host(url)
        if host is not None:
            return McpEdge(peer_host=host, edge_class=classify_host(host), server_kind="streamable-http")
    if kind == "streamable-http":
        # Declared HTTP but no resolvable URL: fall back to the server name, still
        # HTTP-classified.
        host = server_name if server_name is not None else UNKNOWN_MCP_SERVER
        return McpEdge(peer_host=host, edge_class=classify_host(host), server_kind="streamable-http")
    return McpEdge(
        peer_host=server_name if server_name is not None else UNKNOWN_MCP_SERVER,
        edge_class="local-process",
        server_kind="stdio",
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
