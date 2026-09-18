"""IBAN - locate a ``CC##`` head and its groups, let mod-97 + the registry DECIDE."""

from __future__ import annotations

from typing import NamedTuple

from ..chars import char_at, is_alnum_at, is_digit_at, is_letter_at, is_word_char_at
from ..recognizer import ScanContext, Span
from ..tokens import PatternId
from ..validators.iban import is_iban

#: ISO 13616 length bounds of the stripped (separator-free) IBAN.
MIN_LEN = 15
MAX_LEN = 34


class _Group(NamedTuple):
    start: int
    end: int


class _IbanRecognizer:
    """LOCATES a ``CC##`` head (2 letters, 2 digits) at a word boundary and consumes
    alphanumeric groups separated by single spaces (electronic ``DE89370400...`` and
    print ``DE89 3704 0044 ...`` formats). Because prose can follow a print-format
    IBAN with a space, candidates are tried longest-first, dropping trailing groups,
    until the validator accepts one.
    """

    id: PatternId = "IBAN"

    def find(self, text: str, ctx: ScanContext) -> list[Span]:
        spans: list[Span] = []
        i = 0
        n = len(text)
        while i < n:
            head = (
                is_letter_at(text, i)
                and is_letter_at(text, i + 1)
                and is_digit_at(text, i + 2)
                and is_digit_at(text, i + 3)
            )
            if not head or is_word_char_at(text, i - 1):
                i += 1
                continue
            # Consume groups: a maximal alnum run, then optionally one space followed by alnum.
            groups: list[_Group] = []
            pos = i
            stripped = 0
            while True:
                start = pos
                while is_alnum_at(text, pos):
                    pos += 1
                if pos == start:
                    break
                groups.append(_Group(start, pos))
                stripped += pos - start
                if stripped >= MAX_LEN:
                    break
                if char_at(text, pos) == " " and is_alnum_at(text, pos + 1):
                    pos += 1
                    continue
                break
            matched = False
            length = stripped
            for e in range(len(groups) - 1, -1, -1):
                g = groups[e]
                if e < len(groups) - 1:
                    length -= groups[e + 1].end - groups[e + 1].start
                if length < MIN_LEN:
                    break
                if length > MAX_LEN or is_word_char_at(text, g.end):
                    continue
                candidate = text[i : g.end]
                if is_iban(candidate):
                    spans.append(Span(i, g.end))
                    i = g.end
                    matched = True
                    break
            if not matched:
                i += 1
        return spans


IBAN_RECOGNIZER = _IbanRecognizer()
