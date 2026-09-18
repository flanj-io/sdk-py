"""Say something, once, the first time capture fails.

Every capture step in this SDK is fenced: a failure means "we stopped collecting",
never "the agent broke". That is the right trade - but it also means a broken
capture path is completely silent, and the failure mode of silence is a user who
believes they have coverage they do not have. A collector showing nothing looks
exactly like an application making no calls.

So: the FIRST failure prints one line to stderr, and nothing after it. Not a logger
(this SDK does not own the application's logging configuration, and a library that
starts emitting into someone's log pipeline is its own problem), and not per-call
(a failing capture path fails on every call, and a flood is how people learn to
ignore a warning).

The TypeScript SDK has the same one-line-once behaviour for its export failures, for
the same reason.
"""

from __future__ import annotations

import os
import sys

_warned = False

#: Set to any non-empty value to silence the warning (a user who has read it once).
SILENCE_ENV = "FLANJ_SILENCE_CAPTURE_WARNINGS"


def warn_capture_failed(exc: BaseException, what: str) -> None:
    """Print one line, once, naming what failed and why."""
    global _warned
    if _warned:
        return
    _warned = True
    if os.environ.get(SILENCE_ENV):
        return
    try:
        print(
            f"[flanj] {what} failed and capture has stopped for it: "
            f"{type(exc).__name__}: {exc}. Your application is unaffected; this is the only "
            f"warning. Set {SILENCE_ENV}=1 to silence it.",
            file=sys.stderr,
        )
    except Exception:
        pass  # a broken stderr must not become the failure we were reporting


def _reset_for_tests() -> None:
    """Test-only: forget that a warning was printed."""
    global _warned
    _warned = False
