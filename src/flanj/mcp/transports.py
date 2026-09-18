"""Transport detection: learn where an MCP server is by watching its transport open.

A JavaScript MCP ``Client`` keeps a reference to its transport, and the transport
knows its URL, so the TypeScript SDK reads ``client.transport.url``. A Python
``ClientSession`` is built from two in-memory streams and holds nothing else; the
URL belongs to ``streamable_http_client`` (or ``sse_client`` / ``stdio_client``),
which runs as a separate task. There is no reference from the session to the URL.

So the SDK learns it at the one moment it is known: when the transport OPENS.
:func:`patch_transport_openers` wraps each opener; the wrapper records the URL (or
``stdio``) on the streams it yields, and the session wrapper reads that tag back
from the streams the session was built with.

This only works for transports opened AFTER the patch. Code that did
``from mcp.client.stdio import stdio_client`` before flanj loaded holds the original
function - which is why flanj is loaded first (``import flanj.register`` or
``flanj.start()``), exactly as Datadog's ``import ddtrace.auto`` and our own
``node -r @flanj/sdk/register`` are. A session whose transport was never seen is
classified ``unknown``, never guessed (see ``resolve_edge``).

Out of band like everything else here: the wrapper returns the opener's own streams,
awaits nothing of its own, and re-raises every exception untouched.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: Attribute the tag is stored under on each yielded stream object.
_TAG_ATTR = "__flanj_transport__"
#: Marks a function this module already wrapped (patching is idempotent).
_WRAPPED_ATTR = "__flanj_wrapped_opener__"


@dataclass(frozen=True)
class TransportTag:
    #: ``streamable-http`` for every URL-addressed transport (streamable HTTP, SSE,
    #: websocket - the TypeScript SDK treats any transport with a URL the same way),
    #: or ``stdio`` for a server the app launched as a child process.
    kind: str
    url: str | None = None
    #: stdio only: ``(command, *args)`` as the client launched the server. Never
    #: the environment or working directory.
    command: tuple[str, ...] | None = None


# (module, function name, tag builder). The streamable-HTTP opener has two names:
# `streamablehttp_client` on the 1.x line, `streamable_http_client` on both.
def _url_tag(args: tuple[Any, ...], kwargs: dict[str, Any]) -> TransportTag:
    url = kwargs.get("url", args[0] if args else None)
    return TransportTag(kind="streamable-http", url=str(url) if url is not None else None)


def _stdio_tag(args: tuple[Any, ...], kwargs: dict[str, Any]) -> TransportTag:
    params = kwargs.get("server", args[0] if args else None)
    command = getattr(params, "command", None)
    argv = getattr(params, "args", None) or []
    if isinstance(command, str) and command:
        return TransportTag(kind="stdio", command=(command, *[str(a) for a in argv]))
    return TransportTag(kind="stdio")


_OPENERS: tuple[tuple[str, str, Callable[[tuple[Any, ...], dict[str, Any]], TransportTag]], ...] = (
    ("mcp.client.streamable_http", "streamable_http_client", _url_tag),
    ("mcp.client.streamable_http", "streamablehttp_client", _url_tag),
    ("mcp.client.sse", "sse_client", _url_tag),
    ("mcp.client.websocket", "websocket_client", _url_tag),
    ("mcp.client.stdio", "stdio_client", _stdio_tag),
)

#: Modules that re-export an opener under the same object. Patching only the
#: defining module would miss `from mcp import stdio_client` and the higher-level
#: `mcp.client.client.Client` (2.x), which imports the openers itself.
_REEXPORTERS = (
    "mcp",
    "mcp.client",
    "mcp.client.client",
    "mcp.client.session_group",
    "mcp.client.__main__",
)


#: How far to follow `_inner` wrappers. mcp 2.x wraps its HTTP streams once
#: (`ContextSendStream._inner` -> an anyio stream); the bound keeps a hostile
#: object from walking us in circles.
_MAX_UNWRAP = 3


def _layers(obj: Any) -> list[Any]:
    """The stream and the streams it wraps, outermost first."""
    layers: list[Any] = []
    for _ in range(_MAX_UNWRAP + 1):
        if obj is None:
            break
        layers.append(obj)
        try:
            obj = getattr(obj, "_inner", None)
        except Exception:
            break
    return layers


def tag_of(obj: Any) -> TransportTag | None:
    """The tag recorded on a stream or on a stream it wraps, or None. Never raises."""
    for layer in _layers(obj):
        try:
            tag = getattr(layer, _TAG_ATTR, None)
        except Exception:
            continue
        if isinstance(tag, TransportTag):
            return tag
    return None


def _tag_streams(streams: Any, tag: TransportTag) -> None:
    """Record ``tag`` on each yielded stream.

    The mcp 2.x HTTP transport yields ``ContextSendStream`` / ``ContextReceiveStream``,
    which declare ``__slots__`` and so refuse new attributes. Each wraps an anyio
    stream in ``_inner`` that does accept one, so the tag goes on the first layer
    that takes it. This failed silently the first time: the tag was simply absent
    and every HTTP session read as ``unknown``.
    """
    if not isinstance(streams, tuple):
        return
    for stream in streams:
        for layer in _layers(stream):
            try:
                setattr(layer, _TAG_ATTR, tag)
                break
            except Exception:
                continue


class _TaggingContextManager:
    """Delegates to the opener's own async context manager, tagging what it yields."""

    __slots__ = ("_inner", "_tag")

    def __init__(self, inner: Any, tag: TransportTag) -> None:
        self._inner = inner
        self._tag = tag

    async def __aenter__(self) -> Any:
        streams = await self._inner.__aenter__()
        _tag_streams(streams, self._tag)
        return streams

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        return await self._inner.__aexit__(exc_type, exc, tb)


def _wrap(original: Callable[..., Any], build_tag: Callable[..., TransportTag]) -> Callable[..., Any]:
    def opener(*args: Any, **kwargs: Any) -> Any:
        inner = original(*args, **kwargs)
        try:
            tag = build_tag(args, kwargs)
        except Exception:
            return inner  # never let tagging change what the caller gets
        return _TaggingContextManager(inner, tag)

    opener.__name__ = getattr(original, "__name__", "opener")
    opener.__qualname__ = getattr(original, "__qualname__", opener.__name__)
    opener.__doc__ = getattr(original, "__doc__", None)
    opener.__wrapped__ = original  # type: ignore[attr-defined]
    setattr(opener, _WRAPPED_ATTR, True)
    return opener


def patch_transport_openers() -> list[str]:
    """Wrap every MCP transport opener that is installed. Idempotent; never raises.

    Returns the dotted names patched on this call. The ``mcp`` package is an
    optional peer: when it is absent this returns an empty list.
    """
    patched: list[str] = []
    for module_name, fn_name, build_tag in _OPENERS:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        original = getattr(module, fn_name, None)
        if not callable(original) or getattr(original, _WRAPPED_ATTR, False):
            continue
        wrapped = _wrap(original, build_tag)
        setattr(module, fn_name, wrapped)
        patched.append(f"{module_name}.{fn_name}")
        for reexporter in _REEXPORTERS:
            try:
                re_module = importlib.import_module(reexporter)
            except Exception:
                continue
            for attr, value in list(vars(re_module).items()):
                if value is original:
                    setattr(re_module, attr, wrapped)
    return patched


def unpatch_transport_openers() -> None:
    """Restore the original openers. For tests; never needed in an application."""
    for module_name, fn_name, _ in _OPENERS:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        current = getattr(module, fn_name, None)
        original = getattr(current, "__wrapped__", None)
        if not getattr(current, _WRAPPED_ATTR, False) or original is None:
            continue
        setattr(module, fn_name, original)
        for reexporter in _REEXPORTERS:
            try:
                re_module = importlib.import_module(reexporter)
            except Exception:
                continue
            for attr, value in list(vars(re_module).items()):
                if value is current:
                    setattr(re_module, attr, original)
