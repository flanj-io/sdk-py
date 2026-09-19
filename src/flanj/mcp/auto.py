"""Auto-instrumentation: patch ``ClientSession`` once, every session instruments itself.

The Python counterpart of the TypeScript SDK's ``auto-instrument.ts``
(``patchMcpClientConstructor`` / ``registerMcpAutoInstrumentation``). The class's
``initialize`` / ``list_tools`` / ``call_tool`` become trampolines: the first call on
an instance binds the ORIGINAL methods onto that instance and runs
:func:`instrument_mcp_client` on it, so every later call goes straight through the
per-instance wrapper. Datadog's MCP integration patches the same three methods on
the same class.

The trampolines are plain functions that return the wrapped coroutine; they add no
``await`` and no frame that could change scheduling. The ``mcp`` package stays an
optional peer: when it is not installed nothing is patched and nothing fails.
"""

from __future__ import annotations

import functools
import importlib
import types
from collections.abc import Callable
from typing import Any

from .instrument import instrument_mcp_client
from .transports import patch_transport_openers, unpatch_transport_openers

_CLASS_PATCHED = "__flanj_class_patched__"
_INSTANCE_MARKER = "__flanj_mcp_instrumented__"
_METHODS = ("initialize", "list_tools", "call_tool")

#: Where the session class lives - the same path on the 1.x and 2.x lines.
_SESSION_CLASSES = (("mcp.client.session", "ClientSession"),)


def patch_client_session_class(cls: Any, **options: Any) -> bool:
    """Make every instance of ``cls`` instrument itself on first use. Idempotent."""
    if not isinstance(cls, type):
        return False
    if not callable(getattr(cls, "call_tool", None)) or not callable(getattr(cls, "list_tools", None)):
        return False
    if _CLASS_PATCHED in cls.__dict__:
        return True
    originals: dict[str, Callable[..., Any]] = {}
    for name in _METHODS:
        fn = getattr(cls, name, None)
        if callable(fn):
            originals[name] = fn
    setattr(cls, _CLASS_PATCHED, originals)

    def ensure_instrumented(instance: Any) -> None:
        if getattr(instance, _INSTANCE_MARKER, False):
            return
        own = vars(instance)
        for name, fn in originals.items():
            if name not in own:
                setattr(instance, name, types.MethodType(fn, instance))
        instrument_mcp_client(instance, **options)

    for name, fn in originals.items():
        setattr(cls, name, _trampoline(name, fn, ensure_instrumented))
    return True


def _trampoline(name: str, fn: Callable[..., Any], ensure: Callable[[Any], None]) -> Callable[..., Any]:
    def trampoline(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            ensure(self)
        except Exception:
            pass  # instrumentation is best-effort; the call itself is not
        own = vars(self).get(name)
        if own is not None:
            return own(*args, **kwargs)
        return fn(self, *args, **kwargs)

    functools.update_wrapper(trampoline, fn)
    return trampoline


def register_mcp_auto_instrumentation(**options: Any) -> list[str]:
    """Patch every installed MCP client session class and transport opener.

    ``options`` are :func:`instrument_mcp_client`'s. Returns what was patched; an
    empty list means no ``mcp`` package is installed.
    """
    patched = patch_transport_openers()
    for module_name, class_name in _SESSION_CLASSES:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        if patch_client_session_class(getattr(module, class_name, None), **options):
            patched.append(f"{module_name}.{class_name}")
    return patched


def unregister_mcp_auto_instrumentation() -> None:
    """Restore the original class methods and openers. For tests."""
    for module_name, class_name in _SESSION_CLASSES:
        try:
            cls = getattr(importlib.import_module(module_name), class_name)
        except Exception:
            continue
        originals = cls.__dict__.get(_CLASS_PATCHED)
        if not originals:
            continue
        for name, fn in originals.items():
            setattr(cls, name, fn)
        delattr(cls, _CLASS_PATCHED)
    unpatch_transport_openers()
