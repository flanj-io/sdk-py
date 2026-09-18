"""Flush on the way out - the TypeScript SDK's ``flush-on-exit.ts``, in Python.

A batching exporter holds records in memory. Without this, the last few seconds
of captured calls are lost whenever the process ends, and a SIGTERM (every
container stop, every deploy) loses them always.

- normal interpreter exit: a bounded flush (``atexit``);
- SIGTERM / SIGINT: a bounded shutdown, then the PREVIOUS handler runs, so the
  process still exits, raises ``KeyboardInterrupt`` or does whatever it did
  before - flush first, never instead.

Signal handlers can only be installed from the main thread; elsewhere only the
``atexit`` part is installed.
"""

from __future__ import annotations

import atexit
import os
import signal
import threading
from typing import Any

#: Same bound as the TypeScript SDK: a hung collector must not hold the process.
FLUSH_TIMEOUT_MILLIS = 5000

_SIGNALS = ("SIGTERM", "SIGINT")


def flush_on_exit(handle: Any) -> None:
    atexit.register(_bounded_flush, handle)
    if threading.current_thread() is not threading.main_thread():
        return
    for name in _SIGNALS:
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        try:
            previous = signal.getsignal(signum)
            signal.signal(signum, _handler(handle, signum, previous))
        except (ValueError, OSError):
            continue


def _bounded_flush(handle: Any) -> None:
    try:
        handle.flush(FLUSH_TIMEOUT_MILLIS)
    except Exception:
        pass


def _handler(handle: Any, signum: int, previous: Any) -> Any:
    def on_signal(received: int, frame: Any) -> None:
        try:
            handle.shutdown()
        except Exception:
            pass
        # Then behave exactly as before we were installed.
        signal.signal(signum, previous if previous is not None else signal.SIG_DFL)
        if callable(previous):
            previous(received, frame)
        elif previous == signal.SIG_IGN:
            return
        else:
            os.kill(os.getpid(), signum)

    return on_signal
