"""The two cases in which a NUMBER is redacted.

A JSON number literal on the text path, or a number value on the structural
path. Everything else numeric is left untouched:

- a 3-4 digit integer under a CVV key -> CVV;
- a 13-19 digit integer that passes Luhn -> PAN (a PAN sent as a bare number).
"""

from __future__ import annotations

from .chars import is_digit_at
from .luhn import passes_luhn
from .recognizers.cvv import is_cvv_key
from .tokens import PatternId


def classify_integer_digits(digits: str, key: str | None) -> PatternId | None:
    """The pattern that fires for an integer literal's digit string, or None.

    ``digits`` is the literal's digit string (sign, fraction and exponent make it
    not an integer => never redacted).
    """
    if not digits:
        return None
    for i in range(len(digits)):
        if not is_digit_at(digits, i):
            return None
    if 3 <= len(digits) <= 4 and is_cvv_key(key):
        return "CVV"
    if 13 <= len(digits) <= 19 and passes_luhn(digits):
        return "PAN"
    return None


def integer_digits_of(n: object) -> str | None:
    """Digit string of a number when it is a safe-to-print integer; None otherwise.

    Mirrors the JavaScript guard: ``Number.isInteger`` plus the ``1e21`` bound at
    which ``String()`` switches to exponent form. ``bool`` is NOT a number here
    (JavaScript booleans are not numbers either).
    """
    if isinstance(n, bool):
        return None
    if isinstance(n, int):
        if abs(n) >= 10**21:
            return None
        return str(abs(n))
    if isinstance(n, float):
        if n != n or n in (float("inf"), float("-inf")):
            return None
        if not n.is_integer():
            return None
        if abs(n) >= 1e21:
            return None
        return str(abs(int(n)))
    return None
