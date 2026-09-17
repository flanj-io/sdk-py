"""Credential recognizer - format-anchored secret shapes.

Secrets have no checksum library; these are format-anchored shapes (the JWT
additionally validates that its header decodes to a JSON object). Overlapping
hits (e.g. ``Bearer sk_live_...``) keep the longest span.
"""

from __future__ import annotations

import base64
import binascii
import json
import re

from ..recognizer import ScanContext, Span
from ..tokens import PatternId

#: ``sk_live_...``, ``sk_test_...``, ``pk_live_...``, ``rk_test_...``
#: (two lowercase letters, a live/test environment, >= 6 key chars).
_SECRET_KEY = re.compile(r"\b[a-z]{2}_(?:live|test)_[A-Za-z0-9]{6,}")

#: Three base64url segments starting with ``eyJ`` (``{"``). The header is VALIDATED below.
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}")

#: ``Bearer <token>`` (scheme is case-insensitive per RFC 7235); the token is group 1.
_BEARER = re.compile(r"\bbearer\s+([A-Za-z0-9._~+/=-]{8,})", re.IGNORECASE)


def _is_jose_header(segment: str) -> bool:
    """Decode a base64url segment and require a JSON object - a real JOSE header."""
    try:
        padded = segment + "=" * (-len(segment) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        parsed = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return False
    return isinstance(parsed, dict)


class _TokenRecognizer:
    id: PatternId = "TOKEN"

    def find(self, text: str, ctx: ScanContext) -> list[Span]:
        found: list[Span] = []

        for m in _SECRET_KEY.finditer(text):
            found.append(Span(m.start(), m.end()))

        for m in _JWT.finditer(text):
            matched = m.group(0)
            header = matched[: matched.index(".")]
            if _is_jose_header(header):
                found.append(Span(m.start(), m.end()))

        for m in _BEARER.finditer(text):
            tok = m.group(1)
            start = m.end() - len(tok)
            found.append(Span(start, start + len(tok)))

        # Sort by start, longest first; drop anything overlapping an accepted span.
        found.sort(key=lambda s: (s.start, -s.end))
        spans: list[Span] = []
        for s in found:
            if spans and s.start < spans[-1].end:
                continue
            spans.append(s)
        return spans


TOKEN_RECOGNIZER = _TokenRecognizer()
