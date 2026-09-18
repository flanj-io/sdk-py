"""IP recognizer (OPTIONAL - off by default).

IPs are identifiers more often than PII and over-redact peer hosts, so the floor
leaves them unless asked (``include_ip=True``).
"""

from __future__ import annotations

import re

from ..chars import char_at, is_word_char_at
from ..recognizer import ScanContext, Span
from ..tokens import PatternId
from ..validators.ip import is_ip

#: Dotted quad shape; :func:`is_ip` (v4) decides (rejects 256.1.1.1 etc.).
_IPV4_CANDIDATE = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")
#: Hex groups with >= 2 colons (covers ``::1``, ``2001:db8::1``); :func:`is_ip` (v6) decides.
_IPV6_CANDIDATE = re.compile(r"(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}")


def _bounded(text: str, start: int, end: int, extra: str) -> bool:
    before = char_at(text, start - 1)
    after = char_at(text, end)
    if is_word_char_at(text, start - 1) or is_word_char_at(text, end):
        return False
    return (before or " ") not in extra and (after or " ") not in extra


class _IpRecognizer:
    id: PatternId = "IP"

    def find(self, text: str, ctx: ScanContext) -> list[Span]:
        spans: list[Span] = []
        for m in _IPV4_CANDIDATE.finditer(text):
            start, end = m.start(), m.end()
            if _bounded(text, start, end, ".") and is_ip(m.group(0), 4):
                spans.append(Span(start, end))
        for m in _IPV6_CANDIDATE.finditer(text):
            start, end = m.start(), m.end()
            if len(m.group(0)) < 2:
                continue
            if _bounded(text, start, end, ":.") and is_ip(m.group(0), 6):
                spans.append(Span(start, end))
        spans.sort(key=lambda s: s.start)
        out: list[Span] = []
        for s in spans:
            if out and s.start < out[-1].end:
                continue
            out.append(s)
        return out


IP_RECOGNIZER = _IpRecognizer()
