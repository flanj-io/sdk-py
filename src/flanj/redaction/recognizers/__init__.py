"""The mandatory floor, in APPLICATION order.

Earlier recognizers consume structure that would otherwise confuse later ones:

- TOKEN and IBAN take their digit runs before the PAN chain scan sees them;
- PHONE runs before PAN: the phone locator is ``+``-anchored so it can never eat
  a PAN, but the PAN chain scan CAN eat a phone's national part plus trailing
  digits when they happen to pass Luhn (``+1 415 555 2671 1225``), so phone must
  claim its span first.

Reporting order is separate (see ``report_order.py``). The Go collector and the
TypeScript package apply the identical order.
"""

from __future__ import annotations

from ..recognizer import Recognizer
from .cvv import CVV_RECOGNIZER
from .email import EMAIL_RECOGNIZER
from .iban import IBAN_RECOGNIZER
from .ip import IP_RECOGNIZER
from .pan import PAN_RECOGNIZER
from .phone import PHONE_RECOGNIZER
from .ssn import SSN_RECOGNIZER
from .token import TOKEN_RECOGNIZER

DEFAULT_RECOGNIZERS: tuple[Recognizer, ...] = (
    TOKEN_RECOGNIZER,
    CVV_RECOGNIZER,
    IBAN_RECOGNIZER,
    PHONE_RECOGNIZER,
    PAN_RECOGNIZER,
    EMAIL_RECOGNIZER,
    SSN_RECOGNIZER,
)

#: The optional IP recognizer, appended last when ``include_ip`` is set.
OPTIONAL_IP_RECOGNIZER = IP_RECOGNIZER

__all__ = [
    "DEFAULT_RECOGNIZERS",
    "OPTIONAL_IP_RECOGNIZER",
    "TOKEN_RECOGNIZER",
    "CVV_RECOGNIZER",
    "IBAN_RECOGNIZER",
    "PHONE_RECOGNIZER",
    "PAN_RECOGNIZER",
    "EMAIL_RECOGNIZER",
    "SSN_RECOGNIZER",
    "IP_RECOGNIZER",
]
