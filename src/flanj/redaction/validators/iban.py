"""IBAN validation: ISO 13616 mod-97 checksum plus the per-country length registry.

The TypeScript mirror hands its candidates to ``validator``'s ``isIBAN``; the Go
collector and this package own the equivalent check so the floor stays free of any
network-capable dependency for this pattern (``python-stdnum`` would supply it, but
``stdnum/util.py`` imports ``ssl`` at module scope). The registry below is copied
from the Go collector's ``iban.go``, which derived it from that validator's country
table - so all three languages accept the same countries.

Pure, no I/O.
"""

from __future__ import annotations

from typing import Final

#: Stripped (separator-free) length per ISO 3166 country code. A country missing
#: from the registry is not a valid IBAN (fail-closed, like the TypeScript
#: validator, which only knows these countries).
IBAN_LENGTHS: Final[dict[str, int]] = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22,
    "BH": 22, "BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24, "DE": 22,
    "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18, "FO": 18, "FR": 27,
    "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28, "HR": 21, "HU": 28,
    "IE": 22, "IL": 23, "IQ": 23, "IR": 26, "IS": 26, "IT": 27, "JO": 30, "KW": 30,
    "KZ": 20, "LB": 28, "LC": 32, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "MC": 27,
    "MD": 24, "ME": 22, "MK": 19, "MR": 27, "MT": 31, "MU": 30, "MZ": 25, "NL": 18,
    "NO": 15, "PK": 24, "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22,
    "SA": 24, "SC": 31, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "SV": 28, "TL": 23,
    "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
}


def _mod97(stripped: str) -> int:
    """ISO 7064 mod-97-10 remainder.

    Move the first four characters to the end, map A..Z to 10..35, and reduce the
    resulting digit string modulo 97 in a single streaming pass (equivalent to the
    TypeScript validator's chunked reduction).
    """
    rearranged = stripped[4:] + stripped[:4]
    n = 0
    for ch in rearranged:
        if "0" <= ch <= "9":
            n = (n * 10 + (ord(ch) - 48)) % 97
        else:
            n = (n * 100 + (ord(ch) - 65) + 10) % 97  # 10..35, always two digits
    return n


def is_iban(value: str) -> bool:
    """True when ``value`` (possibly print-formatted with spaces, possibly lowercase)
    is a valid IBAN: spaces removed, ASCII letters uppercased, all alphanumeric,
    length equal to the registry length for its country, and mod-97 remainder 1.
    """
    buf = []
    for ch in value:
        if ch == " ":
            continue
        if "a" <= ch <= "z":
            buf.append(chr(ord(ch) - 32))
        elif ("A" <= ch <= "Z") or ("0" <= ch <= "9"):
            buf.append(ch)
        else:
            return False
    if len(buf) < 4:
        return False
    stripped = "".join(buf)
    want = IBAN_LENGTHS.get(stripped[:2])
    if want is None or len(stripped) != want:
        return False
    return _mod97(stripped) == 1
