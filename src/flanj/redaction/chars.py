"""ASCII character classes used for recognizer ANCHORING.

Candidates are anchored against "word" characters so a sensitive run glued to
letters/digits/underscore inside an identifier is not a candidate, and a digit
run is never split. Kept ASCII-only so the Go mirror (``internal/redact``) and
the TypeScript package are byte-identical. ``i`` may be out of range; that
counts as a boundary.
"""

from __future__ import annotations


def is_digit_at(s: str, i: int) -> bool:
    if i < 0 or i >= len(s):
        return False
    return "0" <= s[i] <= "9"


def is_letter_at(s: str, i: int) -> bool:
    if i < 0 or i >= len(s):
        return False
    c = s[i]
    return ("A" <= c <= "Z") or ("a" <= c <= "z")


def is_alnum_at(s: str, i: int) -> bool:
    return is_digit_at(s, i) or is_letter_at(s, i)


def is_word_char_at(s: str, i: int) -> bool:
    """``[A-Za-z0-9_]`` - the anchoring class. Out of range => False (a boundary)."""
    if i < 0 or i >= len(s):
        return False
    return is_alnum_at(s, i) or s[i] == "_"


def char_at(s: str, i: int) -> str:
    return s[i] if 0 <= i < len(s) else ""
