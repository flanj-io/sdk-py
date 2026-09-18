"""Email - locate the shape, let the grammar validator DECIDE."""

from __future__ import annotations

import re

from ..recognizer import ScanContext, Span
from ..tokens import PatternId
from ..validators.email import is_email

#: Local part, ``@``, dotted domain with an alphabetic TLD (>= 2). Shape only -
#: :func:`is_email` decides.
_EMAIL_CANDIDATE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

#: Characters the candidate shape allows at the start but an address cannot begin with.
_LEADING_TRIM = frozenset("._%+-")


class _EmailRecognizer:
    id: PatternId = "EMAIL"

    def find(self, text: str, ctx: ScanContext) -> list[Span]:
        spans: list[Span] = []
        for m in _EMAIL_CANDIDATE.finditer(text):
            start = m.start()
            end = m.end()
            while start < end and text[start] in _LEADING_TRIM:
                start += 1
            candidate = text[start:end]
            if candidate and is_email(candidate):
                spans.append(Span(start, end))
        return spans


EMAIL_RECOGNIZER = _EmailRecognizer()
