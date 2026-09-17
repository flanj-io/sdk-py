"""Readers for the ``_meta`` conventions of MCP protocol revision **2026-07-28**.

That revision removed the ``initialize`` / ``notifications/initialized`` handshake
and protocol-level sessions. Everything the instrumentation used to learn once, at
connect time, now arrives on EVERY result instead:

- ``_meta["io.modelcontextprotocol/serverInfo"]`` - the server's own name and
  version. This is not a nicety: it is the ONLY remaining source of the stdio edge
  key (:func:`resolve_mcp_edge` keys a local-process edge by ``serverInfo.name``),
  and it is the corroboration that lets a provider tie an observation to one of
  their own releases.
- ``traceparent`` / ``tracestate`` / ``baggage`` - W3C trace context, now with a
  documented ``_meta`` convention.
- ``resultType`` - ``complete`` or ``input_required``. NOT under ``_meta``: it is a
  top-level result field, read here so every caller reads it one way.

Every function is read-only, total, and never raises: a hostile or malformed server
must degrade capture, never the app. Unknown values pass through verbatim rather
than being coerced to a known set - this collector reports what it saw.

Results arrive as either the official ``mcp`` package's pydantic models or plain
dicts (a hand-rolled client, a test double), so every read goes through
:func:`_get`, which tries attribute access and mapping access and swallows a
hostile descriptor either way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: The ``_meta`` key servers identify themselves under (revision 2026-07-28).
SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"

#: The ``_meta`` key a task-bearing result references its task under.
RELATED_TASK_META_KEY = "io.modelcontextprotocol/related-task"

#: ``resultType`` values this build knows by name. Others are carried verbatim.
RESULT_TYPE_COMPLETE = "complete"
RESULT_TYPE_INPUT_REQUIRED = "input_required"

_HEX = re.compile(r"^[0-9a-fA-F]+$")
_ALL_ZERO = re.compile(r"^0+$")


@dataclass
class MetaServerInfo:
    """Server identity as read off one result's ``_meta``. All fields optional."""

    name: str | None = None
    version: str | None = None
    protocol_version: str | None = None


@dataclass
class MetaTraceContext:
    """W3C trace context as read off one result's ``_meta``."""

    trace_id: str | None = None
    span_id: str | None = None


@dataclass
class CatalogCacheHints:
    """Catalog cache directives a ``tools/list`` result carries (revision 2026-07-28)."""

    ttl_ms: float | None = None
    cache_scope: str | None = None


def _get(obj: Any, key: str) -> Any:
    """Read one field off a pydantic model or a plain mapping; never raises."""
    if obj is None:
        return None
    try:
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)
    except Exception:
        return None  # hostile getter - feature detection never raises


def _snake(camel: str) -> str:
    out = []
    for ch in camel:
        if ch.isupper():
            out.append("_")
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def get_field(obj: Any, wire_key: str) -> Any:
    """Read a field by its WIRE name, falling back to the python name.

    The official ``mcp`` package models the protocol with pydantic, exposing
    ``structuredContent`` as the attribute ``structured_content`` (the camelCase form
    is only a serialization alias, and is NOT an attribute). A plain dict from a
    hand-rolled client or a test double uses the wire name. Both are real inputs, so
    every read here tries both spellings.

    This is not defensive padding: reading only the wire name captured an EMPTY body
    from every real mcp 2.x client while the whole unit suite - written against
    camelCase dicts - stayed green. It was the stranger smoke that caught it.
    """
    value = _get(obj, wire_key)
    if value is not None:
        return value
    python_key = _snake(wire_key)
    return _get(obj, python_key) if python_key != wire_key else None


def _meta_of(result: Any) -> dict[str, Any] | None:
    """Read a result's ``_meta`` map, or None when it carries none.

    The official ``mcp`` package exposes the wire field ``_meta`` as the python
    attribute ``meta`` on its models (``_meta`` is its alias), so both names are
    tried - a client on either line must read the same identity.
    """
    if result is None:
        return None
    for key in ("_meta", "meta"):
        raw = _get(result, key)
        if isinstance(raw, dict):
            return raw
        if raw is not None and not isinstance(raw, (str, int, float, bool)):
            # A pydantic model for the meta block: fall back to its field map.
            dumped = _model_dict(raw)
            if dumped is not None:
                return dumped
    return None


def _model_dict(obj: Any) -> dict[str, Any] | None:
    """Best-effort mapping view of a pydantic model, by alias (the wire names)."""
    for attr, kwargs in (("model_dump", {"by_alias": True}), ("dict", {"by_alias": True})):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                dumped = fn(**kwargs)
            except Exception:
                continue
            if isinstance(dumped, dict):
                return dumped
    return None


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def server_info_from_meta(result: Any) -> MetaServerInfo | None:
    """Server identity from ``_meta["io.modelcontextprotocol/serverInfo"]``.

    Returns None - not an empty record - when the key is absent, so callers can tell
    "this result said nothing about the server" from "this result said the server
    has no name". Only a result that actually carries identity may overwrite what we
    already know.
    """
    meta = _meta_of(result)
    if meta is None:
        return None
    raw = meta.get(SERVER_INFO_META_KEY)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raw = _model_dict(raw)
        if raw is None:
            return None
    name = _str(raw.get("name"))
    version = _str(raw.get("version"))
    protocol_version = _str(raw.get("protocolVersion") or raw.get("protocol_version"))
    if name is None and version is None and protocol_version is None:
        return None
    return MetaServerInfo(name=name, version=version, protocol_version=protocol_version)


def trace_context_from_meta(result: Any) -> MetaTraceContext | None:
    """W3C trace context from ``_meta.traceparent``.

    ``traceparent`` is ``<version>-<trace-id>-<parent-id>-<flags>``; only the 32-hex
    trace id and 16-hex span id are lifted, and only when they are well-formed and
    non-zero. A malformed header yields nothing rather than a bogus id - a wrong
    correlation key is worse than a missing one, because it points a provider at
    somebody else's request.
    """
    meta = _meta_of(result)
    if meta is None:
        return None
    traceparent = _str(meta.get("traceparent"))
    if traceparent is None:
        return None
    parts = traceparent.split("-")
    if len(parts) < 4:
        return None
    trace_id, span_id = parts[1], parts[2]
    if not _is_hex(trace_id, 32) or not _is_hex(span_id, 16):
        return None
    if _ALL_ZERO.match(trace_id) or _ALL_ZERO.match(span_id):
        return None  # all-zero = invalid per W3C
    return MetaTraceContext(trace_id=trace_id.lower(), span_id=span_id.lower())


def _is_hex(value: str | None, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and _HEX.match(value) is not None


def result_type_of(result: Any) -> str | None:
    """The result's ``resultType`` (revision 2026-07-28), verbatim.

    ``input_required`` is NORMAL traffic on an interactive tool - the server is
    asking for more input, so the payload is partial by design. It is captured like
    any other call and marked here; what must never happen is a detector treating
    that partial payload as a contract violation or as evidence of a shape. Absent on
    servers still on an older revision, which read as None, not as ``complete``.
    """
    return _str(get_field(result, "resultType"))


def task_id_of(result: Any) -> str | None:
    """The task id when this result is a Tasks HANDLE rather than a payload.

    Long-running work moved to the Tasks extension: ``tools/call`` returns
    ``{task: {taskId, status, ...}}`` immediately and the real payload arrives later
    via ``tasks/get``. Such a result is an ENVELOPE - it describes the task, not what
    the tool returned - so anything that models response shape must skip it rather
    than learn the envelope's fields. Read from the ``task`` object, else from the
    ``related-task`` ``_meta`` key.
    """
    task = _get(result, "task")
    if task is not None:
        task_id = _str(get_field(task, "taskId"))
        if task_id is not None:
            return task_id
    meta = _meta_of(result)
    related = meta.get(RELATED_TASK_META_KEY) if meta else None
    if related is None:
        return None
    if isinstance(related, str):
        return _str(related)
    return _str(get_field(related, "taskId"))


def catalog_cache_hints(result: Any) -> CatalogCacheHints | None:
    """``ttlMs`` / ``cacheScope`` off a ``tools/list`` result.

    Clients are now TOLD to cache catalogs, which is why these matter: the snapshot
    we validate against is whatever the client last fetched, so a tool list may
    legitimately be up to ``ttlMs`` behind the server. Carried on the snapshot so a
    later surface can say how old the contract it checked against may be, instead of
    implying it is live.
    """
    if result is None:
        return None
    ttl = get_field(result, "ttlMs")
    scope = _str(get_field(result, "cacheScope"))
    hints = CatalogCacheHints()
    # `bool` is an `int` subclass in Python; `ttlMs: true` is not a duration.
    if isinstance(ttl, (int, float)) and not isinstance(ttl, bool) and ttl == ttl and ttl >= 0:
        if ttl not in (float("inf"), float("-inf")):
            hints.ttl_ms = ttl
    if scope is not None:
        hints.cache_scope = scope
    if hints.ttl_ms is None and hints.cache_scope is None:
        return None
    return hints
