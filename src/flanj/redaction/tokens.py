"""Redaction token format.

Delimiters are U+27E6 / U+27E7 (``⟦ ⟧``) - regex-stable, will not collide with
JSON/text, and make emitted tokens inert to re-scanning.
"""

from __future__ import annotations

import re
from typing import Final, Literal

TOKEN_OPEN: Final = "⟦"
TOKEN_CLOSE: Final = "⟧"

PatternId = Literal["PAN", "EMAIL", "IBAN", "SSN", "PHONE", "CVV", "TOKEN", "IP"]


def make_token(pattern: PatternId) -> str:
    return f"{TOKEN_OPEN}REDACTED:{pattern}{TOKEN_CLOSE}"


#: Matches any already-emitted redaction token, e.g. ``⟦REDACTED:PAN⟧``.
#: Used to prove idempotency invariants; never used to un-redact.
REDACTED_TOKEN_RE: Final = re.compile(f"{TOKEN_OPEN}REDACTED:[A-Z]+{TOKEN_CLOSE}")
