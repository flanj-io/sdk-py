"""Phone - INTERNATIONAL numbers only; locate the shape, let libphonenumber DECIDE."""

from __future__ import annotations

from ..chars import char_at, is_digit_at, is_word_char_at
from ..recognizer import ScanContext, Span
from ..tokens import PatternId
from ..validators.phone import is_valid_phone_number

#: E.164 bounds: at most 15 digits; below 5 nothing validates anywhere.
MAX_DIGITS = 15
MIN_DIGITS = 5
MAX_GROUPS = 8


class _PhoneRecognizer:
    """``+14155552671``, ``+1 415 555 2671``, ``+1 (415) 555-2671``, ``+49.30.901820``.

    Our code LOCATES ``+`` followed by digit groups joined by single ``space``/``.``/``-``
    and optional parentheses; ``phonenumbers`` DECIDES validity. Candidates are tried
    longest-first, dropping trailing groups (so ``+1 415 555 2671 1225`` finds the
    number and spares the 1225).

    National formats without ``+`` are NOT redacted: without a region they cannot be
    validated, and a loose phone regex is precisely what re-caught Luhn-spared ids.
    """

    id: PatternId = "PHONE"

    def find(self, text: str, ctx: ScanContext) -> list[Span]:
        spans: list[Span] = []
        i = 0
        n = len(text)
        while i < n:
            if char_at(text, i) != "+" or not is_digit_at(text, i + 1) or is_word_char_at(text, i - 1):
                i += 1
                continue
            # Collect digit groups. `ends[g]` is the index just past group g (and its `)` if any).
            ends: list[int] = []
            counts: list[int] = []
            pos = i + 1
            digits = 0
            while True:
                save = pos
                if ends:
                    sep = char_at(text, pos)
                    if sep in (" ", ".", "-"):
                        pos += 1
                paren = False
                if char_at(text, pos) == "(":
                    pos += 1
                    paren = True
                if not is_digit_at(text, pos):
                    pos = save
                    break
                start = pos
                while is_digit_at(text, pos):
                    pos += 1
                count = pos - start
                digits += count
                if paren and char_at(text, pos) == ")":
                    pos += 1
                ends.append(pos)
                counts.append(count)
                if digits > MAX_DIGITS or len(ends) >= MAX_GROUPS:
                    break
            matched = False
            total = digits
            for e in range(len(ends) - 1, -1, -1):
                if e < len(ends) - 1:
                    total -= counts[e + 1]
                if total < MIN_DIGITS:
                    break
                end = ends[e]
                if total > MAX_DIGITS or is_word_char_at(text, end):
                    continue
                candidate = text[i:end]
                if is_valid_phone_number(candidate):
                    spans.append(Span(i, end))
                    i = end
                    matched = True
                    break
            if not matched:
                i += 1
        return spans


PHONE_RECOGNIZER = _PhoneRecognizer()
