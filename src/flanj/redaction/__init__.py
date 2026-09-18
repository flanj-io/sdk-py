"""The Flanj redaction floor.

The mandatory card-number, personal-data and secret redaction applied to every
captured body, at source, before anything is stored or transmitted. It exists in
three languages and must behave identically; ``contracts/redaction-vectors.json``
and ``contracts/redaction-fixtures.json`` - not any implementation - are the
contract. See ``REDACTION.md``.

This package performs NO I/O. That is enforced two ways: ``tests/test_no_network.py``
arms every socket/DNS/subprocess primitive and runs the whole battery, and
``tests/test_import_hygiene.py`` walks the AST of every module here and fails on a
network, filesystem or subprocess import.
"""

from .enhancer import SensitiveField, enhance
from .luhn import passes_luhn
from .props import RedactedField, ValueProps, compute_props
from .recognizer import Recognizer, ScanContext, Span
from .recognizers import (
    CVV_RECOGNIZER,
    DEFAULT_RECOGNIZERS,
    EMAIL_RECOGNIZER,
    IBAN_RECOGNIZER,
    IP_RECOGNIZER,
    PAN_RECOGNIZER,
    PHONE_RECOGNIZER,
    SSN_RECOGNIZER,
    TOKEN_RECOGNIZER,
)
from .redact import redact, redact_detailed
from .redact_headers import DEFAULT_HEADER_ALLOWLIST, redact_headers
from .redactor import Redactor, RedactResult, RedactValueResult, create_redactor
from .report_order import REPORT_ORDER
from .tokens import REDACTED_TOKEN_RE, TOKEN_CLOSE, TOKEN_OPEN, PatternId, make_token

__all__ = [
    "redact",
    "redact_detailed",
    "create_redactor",
    "Redactor",
    "RedactResult",
    "RedactValueResult",
    "Recognizer",
    "ScanContext",
    "Span",
    "compute_props",
    "RedactedField",
    "ValueProps",
    "enhance",
    "SensitiveField",
    "redact_headers",
    "DEFAULT_HEADER_ALLOWLIST",
    "make_token",
    "TOKEN_OPEN",
    "TOKEN_CLOSE",
    "REDACTED_TOKEN_RE",
    "PatternId",
    "REPORT_ORDER",
    "passes_luhn",
    "DEFAULT_RECOGNIZERS",
    "TOKEN_RECOGNIZER",
    "CVV_RECOGNIZER",
    "IBAN_RECOGNIZER",
    "PHONE_RECOGNIZER",
    "PAN_RECOGNIZER",
    "EMAIL_RECOGNIZER",
    "SSN_RECOGNIZER",
    "IP_RECOGNIZER",
]
