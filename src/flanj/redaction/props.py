"""Captured properties of a redacted value.

Computed from the ORIGINAL scalar, at the only moment it still exists, so
downstream consumers (the drift detector) can validate the DECIDABLE spec
constraints of a redacted field (type, min/maxLength) instead of skipping it.
NON-REVERSIBLE by design: these are coarse schema-level facts; never add
anything that narrows the value (no prefixes/suffixes, no entropy, no samples).

Every definition here is part of the cross-language contract (the Go collector
and the TypeScript package compute the identical record; the fixture battery
asserts byte-identical output):

- ``length`` counts UNICODE CODE POINTS of the original scalar text - NOT UTF-16
  units, NOT bytes;
- lower/upper/digit classes are ASCII (a-z / A-Z / 0-9);
- control = code point <= 0x1F or == 0x7F; printable = 0x20-0x7E;
  extended = > 0x7F.
"""

from __future__ import annotations

import re
from typing import Any

from .tokens import TOKEN_CLOSE, TOKEN_OPEN, PatternId

#: Matches a scalar that is EXACTLY one emitted token; group 1 = the pattern id.
WHOLE_TOKEN_RE = re.compile(f"^{TOKEN_OPEN}REDACTED:([A-Z0-9_]+){TOKEN_CLOSE}$")

#: A ``ValueProps`` record. Kept as a plain dict so it serializes to the wire
#: shape verbatim, with the key order the contract fixes.
ValueProps = dict[str, Any]

#: One whole-value redaction: where, what fired, and the original's properties.
#: ``path`` is an RFC 6901 JSON Pointer ('' = the root scalar itself).
RedactedField = dict[str, Any]


def compute_props(text: str, kind: str, integer: bool | None = None) -> ValueProps:
    """Compute the props of an original scalar.

    ``text`` is the scalar's text (a number's literal).
    """
    lower = upper = digits = control = printable = extended = False
    length = 0
    for ch in text:
        length += 1
        c = ord(ch)
        if 0x61 <= c <= 0x7A:
            lower = True
        elif 0x41 <= c <= 0x5A:
            upper = True
        elif 0x30 <= c <= 0x39:
            digits = True
        if c <= 0x1F or c == 0x7F:
            control = True
        elif c <= 0x7E:
            printable = True
        else:
            extended = True
    # Key order is part of the wire contract: `flanj.redaction.fields` is
    # serialized verbatim, and `integer` is appended LAST (numbers only), exactly
    # as the TypeScript package and the Go collector emit it.
    props: ValueProps = {"type": kind, "length": length}
    props["containsLowerCase"] = lower
    props["containsUpperCase"] = upper
    props["containsDigits"] = digits
    props["containsASCIIControlChars"] = control
    props["containsASCIIPrintableChars"] = printable
    props["containsASCIIExtendedChars"] = extended
    if kind == "number":
        props["integer"] = True if integer is None else integer
    return props


def escape_pointer_segment(segment: str) -> str:
    """RFC 6901 segment escaping: ``~`` -> ``~0``, ``/`` -> ``~1``."""
    if "~" not in segment and "/" not in segment:
        return segment
    return segment.replace("~", "~0").replace("/", "~1")


def whole_token_id(value: str) -> PatternId | None:
    """The pattern id when ``value`` is exactly one token, else None."""
    m = WHOLE_TOKEN_RE.match(value)
    return m.group(1) if m else None  # type: ignore[return-value]


def sort_fields(fields: list[RedactedField]) -> list[RedactedField]:
    """Canonical field order: sorted by path (fields never share a path)."""
    return sorted(fields, key=lambda f: f["path"])
