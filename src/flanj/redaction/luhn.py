"""Luhn (mod-10) gate for candidate PANs.

This is the ONLY thing that turns a 13-19 digit run into a PAN hit - the floor is
Luhn-gated, never brand/BIN-gated (BIN tables differ between libraries and reject
real 19-digit and regional cards; Luhn is a fixed function, so all three
implementations agree forever).

Owned rather than borrowed, exactly as the Go collector owns ``luhn.go``:
``python-stdnum`` would supply this, but ``stdnum/util.py`` imports ``ssl`` at
module scope, which drags ``socket``, ``ssl`` and ``subprocess`` into the floor's
module graph. A zero-I/O security floor may not carry a network-capable dependency
for a twelve-line checksum. Luhn is fixed arithmetic, not a heuristic - owning it
costs nothing and is what the Go mirror already does.
"""

from __future__ import annotations


def passes_luhn(digits: str) -> bool:
    """True when an all-digit string passes the Luhn checksum.

    Input must be digits only (the caller has already stripped separators);
    anything else - including the empty string - is False.
    """
    if not digits:
        return False
    total = 0
    double = False
    for ch in reversed(digits):
        if not ("0" <= ch <= "9"):
            return False
        d = ord(ch) - 48
        if double:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        double = not double
    return total % 10 == 0
