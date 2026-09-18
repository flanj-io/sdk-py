"""Wrap an MCP **client session** (v0.5 spec section 4.B).

Strictly out-of-band: the wrapper NEVER changes a call, a result, or an error -
arguments pass through verbatim, results are returned untouched, exceptions
propagate unchanged, and every capture step is fenced so a capture failure means
"we stopped collecting", never "the agent broke".

- ``list_tools`` -> one ``contract_snapshot`` record per COMPLETE list (pagination
  followed via the cursor chain the caller drives).
- ``call_tool``  -> one captured call record on the redacted call shape
  (arguments/result floor-redacted at source).
- JSON-RPC ids are observed on the session's own outgoing messages and labeled
  CLIENT-generated (``flanj.corr.client_request_id``).

Returns the same session instance. Idempotent.

**The async contract, which no redaction fixture can check.**

``call_tool`` and ``list_tools`` are coroutines, so this wrapper is held to three
rules that the string-in/string-out vectors say nothing about. They are asserted
in ``tests/mcp/test_async_transparency.py``, deliberately, because the equivalent
bug class already shipped once in the other runtime (a passive listener that broke
apps reading bodies via ``for await``):

1. **Cancellation passes through untouched.** ``asyncio.CancelledError`` and
   ``trio.Cancelled`` both derive from ``BaseException``, so the ``except
   Exception`` here cannot catch them - and the explicit re-raise above it says so
   to the next reader. A cancelled call is NOT captured: cancellation is the caller
   withdrawing, not an outcome the tool produced, and doing work on that path is
   how a wrapper starts delaying the cancellation it was supposed to be invisible
   to.
2. **No suspension point is added.** The wrapper awaits the wrapped coroutine and
   nothing else; every capture step is synchronous. An extra ``await`` - even
   ``sleep(0)`` - is an extra place the scheduler can interleave, which changes the
   ordering an app observes.
3. **The result is read, never consumed.** Capture serializes a snapshot of the
   result; it holds no reference past the call and iterates nothing, so a streamed
   or lazily-materialized result behaves exactly as it would uninstrumented.
"""

from __future__ import annotations

import contextvars
import time
import weakref
from collections.abc import Callable
from typing import Any

from ..capture_warning import warn_capture_failed, warn_once
from ..config import DEFAULT_BODY_CAP_BYTES
from ..runtime import assert_supported_python
from .assemble_call import assemble_mcp_call
from .assemble_snapshot import assemble_contract_snapshot
from .record import emit_contract_snapshot, emit_mcp_call
from .resolve_edge import EDGE_CLASS_UNKNOWN, resolve_mcp_edge
from .result_meta import _get, catalog_cache_hints, get_field, server_info_from_meta
from .transports import TransportTag, tag_of
from .types import McpCapturedCall, McpContractSnapshot, McpServerIdentity, McpServerKind

_INSTRUMENTED = "__flanj_mcp_instrumented__"
_SEND_OBSERVERS = "__flanj_mcp_send_observers__"

#: Bound on remembered-but-unclaimed JSON-RPC ids (a hostile or odd client cannot
#: grow it without bound).
MAX_PENDING_IDS = 1024

#: Bound on a cursor chain driven by :func:`_refetch_all_tools`.
MAX_PAGES = 1000


#: The session whose wrapped ``call_tool`` is on the stack, as a context variable.
#:
#: The TypeScript SDK attributes a send by marking a registry field for the
#: SYNCHRONOUS window of ``callTool``, which works there because both supported
#: package lines send the JSON-RPC request synchronously inside it. That technique
#: does not port: in Python ``await original_call_tool(...)`` does not return until
#: the whole call completes, so a marker set around it would stay set across every
#: suspension point and two concurrent calls would cross-attribute their ids.
#:
#: A ``ContextVar`` is the correct primitive and is strictly better than the marker:
#: it is per-TASK, so it survives suspension without leaking between concurrent
#: calls, and the dispatcher awaits its write inline on the calling task, which is
#: exactly the context that has it set.
_SENDING_SESSION: contextvars.ContextVar[weakref.ReferenceType[Any] | None] = (
    contextvars.ContextVar("flanj_mcp_sending_session", default=None)
)


class _SendObserverRegistry:
    """Per-dispatcher send-observation registry.

    The dispatcher's write is wrapped exactly ONCE; the registry keys one observer
    per (dispatcher, session), so two instrumented sessions sharing one dispatcher
    each observe only their own requests - and dropping one session's observer (or
    the session being collected; the weak references keep the registry leak-free)
    never breaks the other's observation.
    """

    def __init__(self) -> None:
        self.observers: list[tuple[weakref.ReferenceType[Any], Callable[[Any], None]]] = []

    def deliver(self, message: Any) -> None:
        """Route one outgoing message to the observer of the session sending it."""
        # Self-clean observers whose session was collected.
        self.observers = [(ref, fn) for ref, fn in self.observers if ref() is not None]
        sender_ref = _SENDING_SESSION.get()
        sender = sender_ref() if sender_ref is not None else None
        if sender is not None:
            for ref, fn in self.observers:
                if ref() is sender:
                    fn(message)
                    return
            return
        # No attributed sender (a dispatcher that writes from a task of its own):
        # unambiguous only when a single session observes this dispatcher - never
        # guess between two.
        if len(self.observers) == 1:
            self.observers[0][1](message)


def instrument_mcp_client(
    session: Any,
    *,
    integration: str | None = None,
    endpoint: str | None = None,
    server_kind: McpServerKind | None = None,
    body_cap_bytes: int = DEFAULT_BODY_CAP_BYTES,
    logger: Any = None,
    on_capture: Callable[[McpCapturedCall], None] | None = None,
    on_snapshot: Callable[[McpContractSnapshot], None] | None = None,
    refetch_on_list_changed: bool = True,
) -> Any:
    """Instrument ``session`` in place and return it.

    :param integration: integration id emitted as ``flanj.integration``. When
        omitted it is derived from the edge key exactly as the collector derives one
        from a host (``mcp.acme.com`` -> ``mcp-acme-com``), so every server gets its
        own integration instead of all of them sharing one baseline.
    :param endpoint: streamable-HTTP endpoint URL - the edge key host. Detected
        from the transport when omitted.
    :param server_kind: force the server kind; detected from the transport when
        omitted.
    :param logger: emit records through this OpenTelemetry logger.
    :param on_capture: sink for each captured, redacted tool call.
    :param on_snapshot: sink for each complete observed ``tools/list``.
    :param refetch_on_list_changed: refetch and re-snapshot on
        ``notifications/tools/list_changed``, chained so the application's own
        message handler still runs. Default True - the SAME default as the
        TypeScript SDK's ``refetchOnListChanged``, and deliberately so: two tenants
        watching one MCP server must build the same baseline whatever language
        they are written in, and a divergent default would make them differ
        silently, one layer above anything the shared fixtures can see. The
        refetch runs on the session's own task group, so its lifetime is bounded
        by the session exactly as the Node promise is by the client.
    """
    assert_supported_python()

    if getattr(session, _INSTRUMENTED, False):
        return session
    try:
        setattr(session, _INSTRUMENTED, True)
    except Exception:
        return session  # a frozen/slotted object we cannot instrument: leave it alone

    state: dict[str, Any] = {
        # The in-flight list_tools cursor chain; None = none. `expected_cursor` is
        # the next cursor the chain is waiting for - pages are keyed to the chain by
        # it, so an interleaved chain can never corrupt the accumulator.
        "chain": None,
        # Observed-but-unclaimed client-generated JSON-RPC ids, FIFO per tool name.
        "pending_ids": [],
        # Server identity as last seen in a RESULT's `_meta` - the authoritative
        # source since protocol revision 2026-07-28 removed the handshake. Sticky: a
        # result that says nothing about the server never erases what an earlier one
        # told us.
        "observed_server": McpServerIdentity(),
        # `ttlMs` / `cacheScope` as last seen on a `tools/list` result.
        "catalog_cache": None,
        "refetching": False,
        # Identity from the `initialize` RESULT, observed by our own wrapper. The
        # 1.x `mcp` line keeps only the server's capabilities after the handshake -
        # it discards serverInfo - so this is the only place its name can come from
        # (Datadog's MCP integration reads it the same way). `_meta` still wins.
        "handshake": McpServerIdentity(),
    }

    session_ref = weakref.ref(session)

    # ---- identity + edge -----------------------------------------------------

    def absorb_server_info(result: Any) -> None:
        """Absorb one result's ``_meta`` server identity.

        Called on EVERY result - both ``tools/list`` and ``tools/call`` - before
        anything that needs the edge, because :func:`resolve_mcp_edge` keys a stdio
        (``local-process``) edge by ``serverInfo.name``: without this, every stdio
        server on the host collapses onto the single edge ``unknown-mcp-server``,
        and two servers sharing that key alternate their tool lists into phantom
        ``definition_change`` findings.
        """
        try:
            seen = server_info_from_meta(result)
            if seen is None:
                return
            observed: McpServerIdentity = state["observed_server"]
            if seen.name is not None:
                observed.name = seen.name
            if seen.version is not None:
                observed.version = seen.version
            if seen.protocol_version is not None:
                observed.protocol_version = seen.protocol_version
        except Exception:
            pass  # capture-side only - never disturb the app

    def absorb_handshake(result: Any) -> None:
        """Absorb the ``initialize`` result's serverInfo / protocolVersion / capabilities."""
        try:
            handshake: McpServerIdentity = state["handshake"]
            info = get_field(result, "serverInfo")
            name = get_field(info, "name") if info is not None else None
            version = get_field(info, "version") if info is not None else None
            if isinstance(name, str) and name:
                handshake.name = name
            if isinstance(version, str) and version:
                handshake.version = version
            proto = get_field(result, "protocolVersion")
            if isinstance(proto, str) and proto:
                handshake.protocol_version = proto
            tools = get_field(get_field(result, "capabilities"), "tools")
            list_changed = get_field(tools, "listChanged") if tools is not None else None
            if isinstance(list_changed, bool):
                handshake.list_changed = list_changed
        except Exception:
            pass  # capture-side only - never disturb the app

    def server_identity() -> McpServerIdentity:
        """Server identity, ``_meta`` first and the handshake accessors as fallback.

        The accessors are populated from the ``initialize`` RESULT, which revision
        2026-07-28 deleted - they are empty against a current server and still
        correct against one on an older revision, so they stay as the fallback
        rather than the source.
        """
        identity = McpServerIdentity()
        try:
            init = _get(session, "_initialize_result")
            info = _get(init, "serverInfo") if init is not None else None
            if info is None:
                info = _get(session, "server_info") or _get(session, "_discover_server_info")
            if info is not None:
                name = _get(info, "name")
                version = _get(info, "version")
                if isinstance(name, str):
                    identity.name = name
                if isinstance(version, str):
                    identity.version = version
            proto = _get(session, "_negotiated_version") or _get(session, "protocol_version")
            if isinstance(proto, str):
                identity.protocol_version = proto
            caps = _get(init, "capabilities") if init is not None else None
            list_changed = _get(_get(caps, "tools"), "listChanged") if caps is not None else None
            if isinstance(list_changed, bool):
                identity.list_changed = list_changed
        except Exception:
            pass  # capture-side only - never disturb the app
        # The handshake we observed ourselves fills what the accessors did not keep.
        handshake: McpServerIdentity = state["handshake"]
        if identity.name is None:
            identity.name = handshake.name
        if identity.version is None:
            identity.version = handshake.version
        if identity.protocol_version is None:
            identity.protocol_version = handshake.protocol_version
        if identity.list_changed is None:
            identity.list_changed = handshake.list_changed
        # `_meta` wins: it is per-result and current, where the accessors are a
        # snapshot of a handshake that may not have happened at all.
        observed: McpServerIdentity = state["observed_server"]
        if observed.name is not None:
            identity.name = observed.name
        if observed.version is not None:
            identity.version = observed.version
        if observed.protocol_version is not None:
            identity.protocol_version = observed.protocol_version
        return identity

    def edge() -> tuple[McpServerIdentity, Any]:
        identity = server_identity()
        resolved = resolve_mcp_edge(
            endpoint=endpoint,
            server_kind=server_kind,
            transport=_transport_of(session),
            server_name=identity.name,
            tag=_tag_of_session(session),
        )
        if resolved.edge_class == EDGE_CLASS_UNKNOWN:
            warn_once(
                "mcp-unknown-edge",
                f"[flanj] could not tell whether MCP server '{resolved.peer_host}' is remote or "
                f"local: its transport was opened before flanj was loaded. Its calls are recorded "
                f"without bodies until you load flanj first (import flanj.register, or call "
                f"flanj.start(), before opening MCP transports) or pass endpoint= / server_kind= "
                f"to instrument_mcp_client.",
            )
        return identity, resolved

    def integration_for(e: Any) -> str:
        return integration if integration else integration_for_host(e.peer_host)

    # ---- JSON-RPC id observation ---------------------------------------------

    def observe_sent_message(message: Any) -> None:
        """THIS session's observer: remember its client-generated tools/call ids."""
        try:
            message = _unwrap_jsonrpc(message)
            method = _get(message, "method")
            request_id = _get(message, "id")
            params = _get(message, "params")
            name = get_field(params, "name") if params is not None else None
            if method == "tools/call" and request_id is not None and isinstance(name, str):
                pending: list[dict[str, str]] = state["pending_ids"]
                if len(pending) >= MAX_PENDING_IDS:
                    pending.pop(0)
                pending.append({"tool": name, "id": str(request_id)})
        except Exception:
            pass  # observation only

    def observe_dispatcher_write() -> None:
        """Observe (never alter) the session's outgoing messages.

        The dispatcher's write is wrapped ONCE per dispatcher; this session's
        observer is registered in that dispatcher's per-session registry. Private
        API of the ``mcp`` package, so it is feature-detected and every step is
        fenced: when the seam is not there we simply do not report a correlation
        id, which is an OPTIONAL attribute - we never fail a call over it.
        """
        try:
            seam = _outgoing_seam(session)
            if seam is None:
                return
            owner, method_name = seam
            registry = getattr(owner, _SEND_OBSERVERS, None)
            if registry is None:
                registry = _SendObserverRegistry()
                setattr(owner, _SEND_OBSERVERS, registry)
                original_send = getattr(owner, method_name)

                async def observed_send(message: Any, *args: Any, **kwargs: Any) -> Any:
                    try:
                        registry.deliver(message)
                    except Exception:
                        pass  # observation only
                    return await original_send(message, *args, **kwargs)

                setattr(owner, method_name, observed_send)
            if not any(ref() is session for ref, _ in registry.observers):
                registry.observers.append((session_ref, observe_sent_message))
        except Exception:
            pass  # observation only

    def begin_send_attribution() -> Callable[[], None]:
        """Mark THIS session as the sender for the current task.

        Returns the (idempotent) un-marker, which restores whatever the context held
        before - so a nested instrumented call cannot strand the outer one.
        """
        try:
            token = _SENDING_SESSION.set(session_ref)
        except Exception:
            return _noop
        done = [False]

        def end() -> None:
            if done[0]:
                return
            done[0] = True
            try:
                _SENDING_SESSION.reset(token)
            except (ValueError, RuntimeError):
                # The token belongs to another context (the caller resumed this
                # coroutine elsewhere): clearing is the safe direction.
                _SENDING_SESSION.set(None)

        return end

    def claim_client_request_id(tool: str) -> str | None:
        pending: list[dict[str, str]] = state["pending_ids"]
        for i, entry in enumerate(pending):
            if entry["tool"] == tool:
                return pending.pop(i)["id"]
        return None

    # ---- sinks ---------------------------------------------------------------

    def sink_call(captured: McpCapturedCall) -> None:
        if logger is not None:
            emit_mcp_call(logger, captured)
        if on_capture is not None:
            on_capture(captured)

    def sink_snapshot(snap: McpContractSnapshot) -> None:
        if logger is not None:
            emit_contract_snapshot(logger, snap)
        if on_snapshot is not None:
            on_snapshot(snap)

    def capture_call(tool_name: str, args: Any, result: Any, is_error: bool, started: float) -> None:
        try:
            identity, e = edge()
            sink_call(
                assemble_mcp_call(
                    integration=integration_for(e),
                    peer_host=e.peer_host,
                    edge_class=e.edge_class,
                    server_kind=e.server_kind,
                    tool_name=tool_name,
                    args=args,
                    result=result,
                    is_error=is_error,
                    server_name=identity.name,
                    server_version=identity.version,
                    protocol_version=identity.protocol_version,
                    session_id=_session_id_of(session),
                    client_request_id=claim_client_request_id(tool_name),
                    duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                    body_cap_bytes=body_cap_bytes,
                )
            )
        except Exception as exc:
            # Capture failure = we stopped collecting, never "the agent broke".
            # Silent, except for one line the first time - see capture_warning.
            warn_capture_failed(exc, "capturing an MCP tool call")

    def emit_snapshot_of(tools: list[Any]) -> None:
        try:
            identity, e = edge()
            sink_snapshot(
                assemble_contract_snapshot(
                    integration=integration_for(e),
                    peer_host=e.peer_host,
                    edge_class=e.edge_class,
                    server_kind=e.server_kind,
                    server=identity,
                    tools=tools,
                    cache=state["catalog_cache"],
                )
            )
        except Exception as exc:
            warn_capture_failed(exc, "recording an MCP contract snapshot")

    def accumulate_page(cursor: Any, result: Any) -> None:
        """Fold one list_tools page into the in-flight chain; emit when complete.

        Pages are KEYED to the chain: a head page (no cursor) starts a new chain
        (superseding any in-flight one), and a cursor page is folded in only when its
        cursor is the chain's expected next cursor. A page whose cursor does not
        match the in-flight chain is DISCARDED - a superseded or interleaved chain
        simply produces no snapshot, never a partial or mixed one.
        """
        try:
            # Before anything that resolves the edge: every result carries the
            # server's identity now, and a tools/list result carries the catalog
            # cache directives.
            absorb_server_info(result)
            hints = catalog_cache_hints(result)
            if hints is not None:
                state["catalog_cache"] = hints
            if result is None:
                return
            tools = get_field(result, "tools")
            if not isinstance(tools, (list, tuple)):
                return
            next_cursor = get_field(result, "nextCursor")
            chain = state["chain"]
            if cursor is None:
                chain = {"tools": [], "expected_cursor": None}
                state["chain"] = chain
            elif chain is None or chain["expected_cursor"] != cursor:
                # a page of a chain that is not in flight (head unseen, superseded,
                # or interleaved): discard
                return
            chain["tools"].extend(tools)
            if next_cursor is None or next_cursor == "":
                complete = chain["tools"]
                state["chain"] = None
                emit_snapshot_of(complete)
            else:
                chain["expected_cursor"] = next_cursor
        except Exception:
            state["chain"] = None

    # ---- the two wrapped coroutines -----------------------------------------

    original_initialize = getattr(session, "initialize", None)
    if callable(original_initialize):

        async def initialize(*args: Any, **kwargs: Any) -> Any:
            # No except clause at all: every exception, cancellation included,
            # propagates exactly as it would uninstrumented. Only a successful
            # handshake is read, and reading it is synchronous.
            result = await original_initialize(*args, **kwargs)
            absorb_handshake(result)
            return result

        _install(session, "initialize", initialize, original_initialize)

    original_list_tools = getattr(session, "list_tools", None)
    if callable(original_list_tools):

        async def list_tools(*args: Any, **kwargs: Any) -> Any:
            cursor = _cursor_of(args, kwargs)
            try:
                result = await original_list_tools(*args, **kwargs)
            except BaseException as exc:
                # A failed page ends ITS chain (matched by cursor); never emit a
                # partial list. A failed page of some OTHER chain leaves the
                # in-flight one alone. Cancellation lands here too and is handled
                # the same way - ending a chain is bookkeeping, not capture - and
                # then re-raised untouched by the bare `raise`.
                if isinstance(exc, Exception) or _is_cancellation(exc):
                    chain = state["chain"]
                    if cursor is not None and chain is not None and chain["expected_cursor"] == cursor:
                        state["chain"] = None
                raise
            accumulate_page(cursor, result)
            return result

        _install(session, "list_tools", list_tools, original_list_tools)

    original_call_tool = getattr(session, "call_tool", None)
    if callable(original_call_tool):

        async def call_tool(*args: Any, **kwargs: Any) -> Any:
            observe_dispatcher_write()
            tool_name, tool_args = _parse_call_tool_args(args, kwargs)
            started = time.monotonic()
            end_attribution = begin_send_attribution()
            try:
                result = await original_call_tool(*args, **kwargs)
            except _CANCELLED:
                # Rule 1 of the async contract. Cancellation is the caller
                # withdrawing, not an outcome: capture NOTHING, delay NOTHING,
                # swallow NOTHING. `except Exception` below could not catch these
                # anyway (both derive from BaseException); this clause exists so the
                # next reader cannot widen that one by accident.
                raise
            except Exception:
                # The call happened and failed: record it (no response body), and
                # re-raise untouched.
                capture_call(tool_name, tool_args, None, True, started)
                raise
            else:
                # Identity rides every result now - learn it before resolving the edge.
                absorb_server_info(result)
                capture_call(tool_name, tool_args, result, _is_error_result(result), started)
                return result
            finally:
                # Synchronous, and the only work on the cancellation path.
                end_attribution()

        _install(session, "call_tool", call_tool, original_call_tool)

    if refetch_on_list_changed and hasattr(session, "_message_handler"):
        _install_list_changed_refetch(session, state)

    return session


# --- helpers ------------------------------------------------------------------


def _noop() -> None:
    return None


def _cancellation_types() -> tuple[type[BaseException], ...]:
    """The cancellation exceptions of whichever async backend is installed.

    Both derive from ``BaseException``, so ``except Exception`` never catches them;
    naming them explicitly is what stops a later edit from widening that clause.
    """
    import asyncio

    types: list[type[BaseException]] = [asyncio.CancelledError]
    try:  # trio is optional - anyio runs on either backend
        import trio  # type: ignore[import-not-found]

        types.append(trio.Cancelled)
    except Exception:
        pass
    return tuple(types)


_CANCELLED: tuple[type[BaseException], ...] = _cancellation_types()


def _is_cancellation(exc: BaseException) -> bool:
    return isinstance(exc, _CANCELLED)


def _install(session: Any, name: str, wrapper: Any, original: Any) -> None:
    """Bind ``wrapper`` on the instance, shadowing the class method.

    The original stays reachable for a caller that wants it, and a second
    :func:`instrument_mcp_client` on the same session is a no-op (the instrumented
    marker short-circuits before we get here).
    """
    wrapper.__name__ = getattr(original, "__name__", name)
    wrapper.__doc__ = getattr(original, "__doc__", None)
    wrapper.__wrapped__ = original
    setattr(session, name, wrapper)


def _parse_call_tool_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[str, Any]:
    """Both call shapes: ``call_tool(name, arguments)`` and ``call_tool(name=..., arguments=...)``.

    Also tolerates the TypeScript-style single mapping ``call_tool({"name": ..., "arguments": ...})``
    so a port of JavaScript agent code does not silently record ``unknown-tool``.
    """
    name: Any = kwargs.get("name")
    arguments: Any = kwargs.get("arguments")
    if name is None and args:
        first = args[0]
        if isinstance(first, str):
            name = first
            if arguments is None and len(args) > 1:
                arguments = args[1]
        elif isinstance(first, dict):
            name = first.get("name")
            if arguments is None:
                arguments = first.get("arguments")
    return (name if isinstance(name, str) and name else "unknown-tool"), arguments


def _cursor_of(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """The ``cursor`` of a ``list_tools`` page request, across call shapes."""
    if "cursor" in kwargs:
        return kwargs["cursor"]
    params = kwargs.get("params")
    if params is None and args:
        params = args[0]
    if params is None:
        return None
    if isinstance(params, str):
        return params  # an older line took the cursor positionally
    return get_field(params, "cursor")


def _is_error_result(result: Any) -> bool:
    return get_field(result, "isError") is True


def _transport_of(session: Any) -> Any:
    """The transport reference the edge resolver inspects, read-only."""
    for name in ("_transport", "transport"):
        value = _get(session, name)
        if value is not None:
            return value
    dispatcher = _get(session, "_dispatcher")
    if dispatcher is not None:
        for name in ("_transport", "transport", "_transport_builder"):
            value = _get(dispatcher, name)
            if value is not None:
                return value
    return None


def _tag_of_session(session: Any) -> TransportTag | None:
    """The transport tag on the streams this session was built with, if any."""
    holders = [session, _get(session, "_dispatcher")]
    for holder in holders:
        if holder is None:
            continue
        for name in ("_write_stream", "_read_stream"):
            tag = tag_of(_get(holder, name))
            if tag is not None:
                return tag
    return None


def _outgoing_seam(session: Any) -> tuple[Any, str] | None:
    """Where this session's outgoing JSON-RPC messages pass, as (object, method).

    ``mcp`` 2.x writes through ``session._dispatcher._write(message)``; the 1.x line
    writes ``SessionMessage`` objects to ``session._write_stream.send(...)``. Both are
    private, so both are feature-detected; with neither, no id is reported.
    """
    dispatcher = _get(session, "_dispatcher")
    if dispatcher is not None and callable(getattr(dispatcher, "_write", None)):
        return dispatcher, "_write"
    stream = _get(session, "_write_stream")
    if stream is not None and callable(getattr(stream, "send", None)):
        return stream, "send"
    return None


def _unwrap_jsonrpc(message: Any) -> Any:
    """Peel ``SessionMessage`` and ``JSONRPCMessage`` wrappers down to the request."""
    for attr in ("message", "root"):
        inner = _get(message, attr)
        if inner is not None and not isinstance(inner, (str, int, float, bool)):
            message = inner
    return message


def integration_for_host(host: str) -> str:
    """The collector's own rule for deriving an integration id from a host.

    Byte-identical to ``integrationForHost`` in the collector
    (``extension/flanjui/contracts_upload.go``): ASCII letters lowercased, digits
    kept, everything else a dash, runs of dashes collapsed, dashes trimmed.
    """
    out = []
    for ch in host:
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch)
        elif "A" <= ch <= "Z":
            out.append(chr(ord(ch) + 32))
        else:
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _session_id_of(session: Any) -> str | None:
    value = _get(_transport_of(session), "session_id") or _get(_transport_of(session), "sessionId")
    return value if isinstance(value, str) and value else None


def _install_list_changed_refetch(session: Any, state: dict[str, Any]) -> None:
    """Chain a ``tools/list_changed`` handler that re-drives the wrapped ``list_tools``.

    The Python counterpart of the TypeScript SDK chaining
    ``fallbackNotificationHandler``, installed under the same condition: only when
    the session has the hook (``_message_handler``, which ``ClientSession`` reads at
    call time, so replacing it on the instance is enough).

    The refetch is scheduled on the SESSION's task group, so it can never outlive
    the session. A session that is receiving notifications at all is running inside
    that task group - it is where its dispatcher reads - so the "no task group"
    branch below is defensive, not a behavioural difference: we will not create a
    task group of our own, because a task with a lifetime we do not bound is the
    one thing an out-of-band wrapper must not introduce.

    As in the TypeScript SDK, a change announced while a refetch is already running
    is folded into that refetch rather than starting a second one.
    """
    previous = _get(session, "_message_handler")

    async def handler(message: Any) -> None:
        try:
            method = _get(message, "method") or _get(_get(message, "root"), "method")
            if method == "notifications/tools/list_changed" and not state["refetching"]:
                task_group = _get(session, "_task_group")
                if task_group is not None and hasattr(task_group, "start_soon"):
                    state["refetching"] = True
                    task_group.start_soon(_refetch_all_tools, session, state)
        except Exception:
            pass  # capture-side only
        if callable(previous):
            await previous(message)

    try:
        session._message_handler = handler
    except Exception:
        pass


def _list_tools_page(session: Any, cursor: Any) -> Any:
    """Request one cursor page, in whichever shape this client line accepts.

    The ``mcp`` 2.x line takes ``list_tools(*, params=PaginatedRequestParams(cursor=...))``;
    the 1.x line took ``list_tools(cursor=...)``. Passing the wrong one is a
    ``TypeError`` - which, inside a fenced capture task, would silently end every
    refetch after its first page.
    """
    import inspect

    target = getattr(session.list_tools, "__wrapped__", session.list_tools)
    try:
        takes_params = "params" in inspect.signature(target).parameters
    except (TypeError, ValueError):
        takes_params = False
    if takes_params:
        from mcp import types as mcp_types  # present: this IS an mcp session

        return session.list_tools(params=mcp_types.PaginatedRequestParams(cursor=cursor))
    return session.list_tools(cursor=cursor)


async def _refetch_all_tools(session: Any, state: dict[str, Any]) -> None:
    """Drive the (already wrapped) list_tools through its cursor chain.

    The wrapped path emits the snapshot.
    """
    try:
        cursor: Any = None
        for _ in range(MAX_PAGES):  # bounded: a hostile cursor chain cannot loop forever
            result = await (session.list_tools() if cursor is None else _list_tools_page(session, cursor))
            next_cursor = get_field(result, "nextCursor")
            if next_cursor is None or next_cursor == "":
                return
            cursor = next_cursor
    except Exception:
        return  # capture-side only
    finally:
        state["refetching"] = False
