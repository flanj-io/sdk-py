"""US SSN ``###-##-####`` - format-anchored by definition (an SSN has no checksum)."""

from __future__ import annotations

import re

from ..chars import is_word_char_at
from ..recognizer import ScanContext, Span
from ..tokens import PatternId

#: A bare 9-digit run is deliberately NOT a candidate - that is a common id shape
#: and would over-redact. Anchored against word characters on both sides (a dash
#: neighbour is allowed so ``ssn-123-45-6789`` is still caught).
_SSN_CANDIDATE = re.compile(r"\d{3}-\d{2}-\d{4}")


class _SsnRecognizer:
    id: PatternId = "SSN"

    def find(self, text: str, ctx: ScanContext) -> list[Span]:
        spans: list[Span] = []
        for m in _SSN_CANDIDATE.finditer(text):
            start, end = m.start(), m.end()
            if is_word_char_at(text, start - 1) or is_word_char_at(text, end):
                continue
            spans.append(Span(start, end))
        return spans


SSN_RECOGNIZER = _SsnRecognizer()
