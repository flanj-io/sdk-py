"""PAN - locate digit-group chains structurally, let Luhn DECIDE."""

from __future__ import annotations

from typing import NamedTuple

from ..chars import char_at, is_digit_at, is_word_char_at
from ..luhn import passes_luhn
from ..recognizer import ScanContext, Span
from ..tokens import PatternId

#: PAN length bounds (ISO/IEC 7812) and the most groups a printed PAN uses (4-4-4-4-3).
MIN_DIGITS = 13
MAX_DIGITS = 19
MAX_GROUPS = 5


class _Group(NamedTuple):
    start: int
    end: int


def _digit_groups(s: str) -> list[_Group]:
    """Maximal runs of ASCII digits."""
    groups: list[_Group] = []
    i = 0
    n = len(s)
    while i < n:
        if is_digit_at(s, i):
            start = i
            while is_digit_at(s, i):
                i += 1
            groups.append(_Group(start, i))
        else:
            i += 1
    return groups


def _joinable(s: str, a: _Group, b: _Group) -> bool:
    """Two adjacent groups are joinable when exactly one space or dash separates them."""
    if b.start != a.end + 1:
        return False
    sep = char_at(s, a.end)
    return sep == " " or sep == "-"


class _PanRecognizer:
    """LOCATES candidates structurally - chains of digit groups joined by single
    spaces/dashes (bare, 4-4-4-4, 4-6-5, 4-4-4-4-3, dashed ...) - normalizes them
    to digits, and lets the Luhn validator DECIDE. Detect on normalized digits,
    redact the original span. Anchored: a chain glued to a letter/digit/underscore
    on either side is not a candidate (so ids/hashes/UUIDs never fire and digit
    runs are never split).

    Within a chain every sub-chain of <= MAX_GROUPS groups is tried longest-first
    from each start, left to right, so a PAN preceded or followed by other
    separated digit groups ("ref 1234 4111 1111 1111 1111",
    "4111111111111111 1225") is still found - the classic leftmost-greedy regex
    tests the wrong window and leaks the card.
    """

    id: PatternId = "PAN"

    def find(self, text: str, ctx: ScanContext) -> list[Span]:
        spans: list[Span] = []
        groups = _digit_groups(text)
        i = 0
        while i < len(groups):
            # Build the maximal chain starting at group i.
            j = i
            while j + 1 < len(groups) and _joinable(text, groups[j], groups[j + 1]):
                j += 1
            chain = groups[i : j + 1]

            k = 0
            while k < len(chain):
                matched = False
                # Left anchor: a sub-chain starting mid-chain is preceded by a
                # separator (fine); the chain's first group must not be glued to
                # a word character.
                left_ok = k > 0 or not is_word_char_at(text, chain[0].start - 1)
                if left_ok:
                    last_e = min(len(chain) - 1, k + MAX_GROUPS - 1)
                    for e in range(last_e, k - 1, -1):
                        # Right anchor: a sub-chain ending mid-chain is followed
                        # by a separator.
                        right_ok = e < len(chain) - 1 or not is_word_char_at(text, chain[e].end)
                        if not right_ok:
                            continue
                        digits = "".join(text[chain[g].start : chain[g].end] for g in range(k, e + 1))
                        if len(digits) < MIN_DIGITS:
                            break  # shorter sub-chains only get shorter
                        if len(digits) > MAX_DIGITS:
                            continue
                        if passes_luhn(digits):
                            spans.append(Span(chain[k].start, chain[e].end))
                            k = e + 1
                            matched = True
                            break
                if not matched:
                    k += 1
            i = j + 1
        return spans


PAN_RECOGNIZER = _PanRecognizer()
