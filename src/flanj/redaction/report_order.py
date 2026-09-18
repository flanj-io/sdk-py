"""Canonical order in which fired pattern ids are reported.

Matches the ordering asserted by the golden vectors (e.g. combined bodies report
``["PAN","EMAIL","CVV"]``). Independent of the application order in
``recognizers/__init__.py``.
"""

from __future__ import annotations

from typing import Final

from .tokens import PatternId

REPORT_ORDER: Final[tuple[PatternId, ...]] = (
    "PAN",
    "EMAIL",
    "IBAN",
    "SSN",
    "PHONE",
    "CVV",
    "TOKEN",
    "IP",
)
