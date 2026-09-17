"""Base64 decode-then-scan support (item 3 of the floor's owned responsibilities).

Locates runs that LOOK like base64 (>= MIN_RUN chars of one base64 alphabet,
optional ``=`` padding), decodes them, and hands back the decoded TEXT when -
and only when - it is valid, printable UTF-8. Binary blobs, hashes and ordinary
long words decode to non-text and are never scanned. The caller runs the
recognizers over the decoded text and, on a hit, redacts the WHOLE encoded run.
Depth is 1 (no base64-in-base64).

The shape rules and decode semantics are mirrored exactly by the Go collector
and the TypeScript package: lenient about missing padding and trailing bits,
strict about the alphabet and ``len % 4 == 1``.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import NamedTuple

MIN_RUN = 20
_RUN = re.compile(r"[A-Za-z0-9+/_-]{20,}={0,2}")
_STD = re.compile(r"[+/]")
_URL = re.compile(r"[_-]")


class Base64Run(NamedTuple):
    start: int
    end: int
    decoded: str


def decode_base64_text(run: str) -> str | None:
    """Decode one candidate run; ``None`` when it is not base64 text."""
    body = run.rstrip("=")
    if len(body) < MIN_RUN or len(body) % 4 == 1:
        return None
    std = _STD.search(body) is not None
    url = _URL.search(body) is not None
    if std and url:
        return None
    padded = body + "=" * (-len(body) % 4)
    try:
        data = base64.b64decode(padded, altchars=b"-_" if url else None, validate=True)
    except (binascii.Error, ValueError):
        return None
    # Guard that the whole run was consumed (mirrors the TypeScript length check).
    if len(data) != (len(body) * 3) // 4:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for ch in text:
        c = ord(ch)
        if c < 0x20 and c not in (0x09, 0x0A, 0x0D):
            return None
        if c == 0x7F:
            return None
    return text


def find_base64_runs(text: str) -> list[Base64Run]:
    """Every base64-text run in ``text``, left to right, non-overlapping."""
    runs: list[Base64Run] = []
    for m in _RUN.finditer(text):
        decoded = decode_base64_text(m.group(0))
        if decoded is not None:
            runs.append(Base64Run(m.start(), m.end(), decoded))
    return runs
