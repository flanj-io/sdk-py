"""The supported-Python floor, and the one sentence we refuse below it with.

Stated in exactly three places, each locked by a test
(``tests/test_version_floor.py``) - the same triad the TypeScript SDK keeps for
``engines.node``:

1. ``pyproject.toml``'s ``requires-python``  (what pip refuses to install on)
2. the README's Requirements line             (what a reader is promised)
3. :data:`SUPPORTED_PYTHON` here              (what the code refuses to run on)

Change all three or none.

**Why 3.10.** It is the floor of the official ``mcp`` package itself, so this SDK
can never refuse a runtime the user's own MCP client accepts - a capture library
that is pickier than the thing it captures is a library people uninstall. It is
also the oldest CPython still receiving security fixes. There is a real argument
for 3.11 (native ``ExceptionGroup`` and ``TaskGroup``, and cleaner cancellation
semantics, which is the risk class this SDK cares most about); it was not taken
because the cancellation behaviour we depend on - ``CancelledError`` propagating
untouched through an ``await`` - is identical on 3.10, and is proven so by
``tests/mcp/test_async_transparency.py`` rather than assumed from a version.
"""

from __future__ import annotations

import sys
from typing import Final

#: The minimum supported CPython, as a version tuple.
SUPPORTED_PYTHON: Final[tuple[int, int]] = (3, 10)

#: The same floor as a PEP 440 specifier - the string `pyproject.toml` must carry.
SUPPORTED_PYTHON_SPECIFIER: Final = ">=3.10"


def supported_python_display() -> str:
    return ".".join(str(p) for p in SUPPORTED_PYTHON)


def is_supported_python() -> bool:
    return sys.version_info[:2] >= SUPPORTED_PYTHON


def assert_supported_python() -> None:
    """Fail loudly, and early, on a Python this SDK does not support.

    One sentence, naming the floor, the runtime in hand and why - never a
    traceback into the middle of a capture path.
    """
    if is_supported_python():
        return
    running = ".".join(str(p) for p in sys.version_info[:3])
    raise RuntimeError(
        f"flanj requires Python {SUPPORTED_PYTHON_SPECIFIER} - this is Python {running}, and the "
        f"official `mcp` client package this SDK instruments requires {SUPPORTED_PYTHON_SPECIFIER} "
        f"too, so there is no supported MCP client to capture on it."
    )
