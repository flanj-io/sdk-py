"""CVV - the one CONTEXTUAL recognizer: a bare 3-4 digit number is never a CVV."""

from __future__ import annotations

import re

from ..chars import is_digit_at
from ..recognizer import ScanContext, Span
from ..tokens import PatternId

#: Keys whose value is a card verification code. Case-insensitive; optional
#: ``card_``/``card-`` prefix. (``cid`` is deliberately excluded - it is
#: overwhelmingly "client/customer id".)
_CVV_KEY = re.compile(r"^(?:card[_-]?)?(?:cvv2?|cvc2?|csc|security[_-]?code)$", re.IGNORECASE)

#: ``cvv=123``, ``cvc: 456``, ``"cvv": "789"`` inside free text / form bodies /
#: malformed JSON.
_CVV_TEXT = re.compile(
    r"\b((?:card[_-]?)?(?:cvv2?|cvc2?|csc|security[_-]?code))(\"?\s*[:=]\s*\"?)(\d{3,4})",
    re.IGNORECASE,
)


def is_cvv_key(key: str | None) -> bool:
    """True when ``key`` names a card verification code field.

    Shared with the JSON number path.
    """
    return key is not None and _CVV_KEY.match(key) is not None


def is_cvv_shape(value: str) -> bool:
    """True when ``value`` is exactly a 3-4 digit CVV shape."""
    if len(value) < 3 or len(value) > 4:
        return False
    for i in range(len(value)):
        if not is_digit_at(value, i):
            return False
    return True


class _CvvRecognizer:
    """Two modes.

    - key mode (structured traversal gave us the key): the whole value is
      redacted when the key is a CVV key and the value is a 3-4 digit shape;
    - text mode (no key): ``cvv=123`` / ``cvc: 456`` / ``"cvv":"789"`` forms,
      digits span only.
    """

    id: PatternId = "CVV"

    def find(self, text: str, ctx: ScanContext) -> list[Span]:
        if is_cvv_key(ctx.key) and is_cvv_shape(text):
            return [Span(0, len(text))]
        spans: list[Span] = []
        for m in _CVV_TEXT.finditer(text):
            digits = m.group(3)
            end = m.end()
            if is_digit_at(text, end):
                continue  # 5+ digits is not a CVV shape
            spans.append(Span(end - len(digits), end))
        return spans


CVV_RECOGNIZER = _CvvRecognizer()
