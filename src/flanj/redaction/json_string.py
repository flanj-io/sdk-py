"""Canonical JSON string encoding for REWRITTEN scalars on the text path.

Escapes only what JSON requires (``"``, ``\\``, control chars < 0x20 - short
forms for \\b \\f \\n \\r \\t, lowercase ``\\u00xx`` otherwise); everything else,
including the token glyphs and any non-ASCII, is written raw. This is
byte-identical to JavaScript's ``JSON.stringify`` for well-formed text and is
implemented identically in the Go collector, so a rewritten literal is the same
bytes in all three languages. Untouched literals are never re-encoded at all.
"""

from __future__ import annotations

_SHORT = {
    0x08: "\\b",
    0x0C: "\\f",
    0x0A: "\\n",
    0x0D: "\\r",
    0x09: "\\t",
}


def encode_json_string(s: str) -> str:
    out = ['"']
    for ch in s:
        c = ord(ch)
        if c == 0x22:
            out.append('\\"')
        elif c == 0x5C:
            out.append("\\\\")
        elif c >= 0x20:
            out.append(ch)
        elif c in _SHORT:
            out.append(_SHORT[c])
        else:
            out.append(f"\\u{c:04x}")
    out.append('"')
    return "".join(out)
