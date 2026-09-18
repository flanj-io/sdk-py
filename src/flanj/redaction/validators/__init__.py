"""Hardened validators the recognizers DECIDE with.

The floor borrows validators and owns the pipeline: our recognizers only
*locate* candidates structurally, and every decision to redact is made here or
in a third-party validator (``python-stdnum`` for Luhn and IBAN,
``phonenumbers`` for phone, :mod:`ipaddress` for IP).

``email`` is the exception that proves the rule: no pure-Python email validator
exists without a DNS dependency, and the floor may not pull one into its tree
(REDACTION.md §2, "Fail-closed, zero I/O"). So :func:`is_email` is a direct port
of the *grammar* the other two implementations decide with - ``validator.isEmail``
in TypeScript, ``govalidator.IsEmail`` in Go, both of which are themselves
grammar checks. It lives here, beside the other validators and away from the
locators, because it is a decision function and must stay one.
"""

from .email import is_email
from .iban import is_iban
from .ip import is_ip
from .phone import is_valid_phone_number

__all__ = ["is_email", "is_iban", "is_ip", "is_valid_phone_number"]
