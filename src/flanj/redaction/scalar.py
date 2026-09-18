"""The per-scalar engine.

Protects existing tokens (idempotency / never double-wrap), runs the recognizers
in application order over each unprotected segment, then the base64
decode-then-scan pass. Everything structural above this (objects, arrays, JSON
text, forms) funnels every scalar through here, so one scalar contract serves all
entry points - and the Go collector and the TypeScript package implement the
identical function.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import NamedTuple

from .base64_scan import find_base64_runs
from .recognizer import EMPTY_CONTEXT, Recognizer, ScanContext, Span
from .report_order import REPORT_ORDER
from .tokens import TOKEN_CLOSE, TOKEN_OPEN, PatternId, make_token

#: Matches any already-emitted token; such spans are protected and never re-scanned.
_TOKEN_RE = re.compile(f"{TOKEN_OPEN}REDACTED:[A-Z0-9_]+{TOKEN_CLOSE}")


class ScalarResult(NamedTuple):
    value: str
    #: Pattern ids that fired on THIS scalar (unordered).
    fired: set[PatternId]


def _splice(text: str, spans: Sequence[Span], token: str) -> str:
    """Replace ``spans`` (sorted, non-overlapping) in ``text`` with ``token``."""
    out: list[str] = []
    cursor = 0
    for s in spans:
        out.append(text[cursor : s.start])
        out.append(token)
        cursor = s.end
    out.append(text[cursor:])
    return "".join(out)


def _normalise(spans: Sequence[Span]) -> list[Span]:
    """Defensive normalisation: sort by start and drop overlaps (first wins)."""
    out: list[Span] = []
    for s in sorted(spans, key=lambda x: (x.start, x.end)):
        if s.end <= s.start:
            continue
        if out and s.start < out[-1].end:
            continue
        out.append(s)
    return out


def _apply_recognizers(
    segment: str,
    ctx: ScanContext,
    recognizers: Sequence[Recognizer],
    fired: set[PatternId],
) -> str:
    """Run the recognizers sequentially over one token-free segment."""
    text = segment
    for rec in recognizers:
        spans = _normalise(rec.find(text, ctx))
        if not spans:
            continue
        fired.add(rec.id)
        text = _splice(text, spans, make_token(rec.id))
    return text


def _apply_base64(segment: str, recognizers: Sequence[Recognizer], fired: set[PatternId]) -> str:
    """Decode-then-scan every base64 run; on a hit the WHOLE run becomes one token."""
    runs = find_base64_runs(segment)
    if not runs:
        return segment
    out: list[str] = []
    cursor = 0
    for run in runs:
        inner: set[PatternId] = set()
        _apply_recognizers(run.decoded, EMPTY_CONTEXT, recognizers, inner)
        if not inner:
            continue
        first = next(pid for pid in REPORT_ORDER if pid in inner)
        fired.update(inner)
        out.append(segment[cursor : run.start])
        out.append(make_token(first))
        cursor = run.end
    out.append(segment[cursor:])
    return "".join(out)


def redact_scalar(value: str, ctx: ScanContext, recognizers: Sequence[Recognizer]) -> ScalarResult:
    fired: set[PatternId] = set()
    if not value:
        return ScalarResult(value, fired)

    def scan(seg: str) -> str:
        if not seg:
            return seg
        return _apply_base64(_apply_recognizers(seg, ctx, recognizers, fired), recognizers, fired)

    out: list[str] = []
    cursor = 0
    for m in _TOKEN_RE.finditer(value):
        out.append(scan(value[cursor : m.start()]))
        out.append(m.group(0))
        cursor = m.end()
    out.append(scan(value[cursor:]))
    return ScalarResult("".join(out), fired)
