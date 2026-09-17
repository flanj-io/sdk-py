"""The TEXT entry point's traversal: how a captured body STRING is redacted.

Bodies arrive as strings (the SDK's capped buffer, the collector's OTLP
attribute, the control plane's reply box). Rather than parse -> clone ->
re-serialize - which would reorder keys / reformat numbers differently in each
language and destroy formatting - the text path SCANS the text and rewrites ONLY
the scalars that fired, in place:

- JSON (first non-space char ``{`` or ``[``): a tolerant scanner walks the text
  tracking object/array nesting and the current key; every string literal is
  decoded, scanned (keys too, values with their key as context), and re-encoded
  canonically only if it changed; number literals are checked for CVV-under-key /
  PAN-as-number; anything the scanner does not understand (malformed or truncated
  bodies) is scanned as plain text as "residue" - so EVERY byte of the body is
  scanned by some path and truncation at the capture cap never hides a scalar.
- form-urlencoded (``k=v&k=v``): each key and value is percent-decoded, scanned
  (values with their key as context, so ``cvv=123`` is contextual and
  ``email=jane%40x.com`` is seen as an address), and re-encoded minimally only if
  it changed.
- anything else: one scalar.

The Go collector and the TypeScript package implement the identical scanner, so
the same body redacts to the same bytes in all three languages.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import NamedTuple

from .chars import char_at, is_digit_at
from .json_string import encode_json_string
from .numbers import classify_integer_digits
from .props import RedactedField, compute_props, escape_pointer_segment, whole_token_id
from .recognizer import EMPTY_CONTEXT, Recognizer, ScanContext
from .scalar import redact_scalar
from .tokens import PatternId, make_token


class TextPathResult(NamedTuple):
    text: str
    fired: set[PatternId]
    #: Whole-value redactions (JSON scanner + root scalar only; unsorted - caller sorts).
    fields: list[RedactedField]


class _Frame:
    __slots__ = ("kind", "state", "key", "index")

    def __init__(self, kind: str, state: str) -> None:
        self.kind = kind  # 'obj' | 'arr'
        self.state = state  # 'key' | 'colon' | 'value' | 'comma'
        self.key: str | None = None
        self.index = 0


_WS = frozenset(" \t\n\r")
_STRUCTURAL = frozenset('"{}[]:,')
_NUMBER_LITERAL = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_HAS_WHITESPACE = re.compile(r"\s")
_PERCENT_ESCAPE = re.compile(r"^[0-9A-Fa-f]{2}$")


def redact_text_path(text: str, recognizers: Sequence[Recognizer]) -> TextPathResult:
    fired: set[PatternId] = set()
    fields: list[RedactedField] = []
    if not text:
        return TextPathResult(text, fired, fields)
    i = 0
    while i < len(text) and text[i] in _WS:
        i += 1
    first = char_at(text, i)
    if first == "{" or first == "[":
        return TextPathResult(_scan_json(text, recognizers, fired, fields), fired, fields)
    # Form pairs carry no fields (spec-addressable form bodies are a later enhancement).
    if is_form_body(text):
        return TextPathResult(_scan_form(text, recognizers, fired), fired, fields)
    out = _scalar(text, EMPTY_CONTEXT, recognizers, fired)
    # A top-level scalar body wholly redacted reports the RFC 6901 root path ''.
    if out != text:
        pattern = whole_token_id(out)
        if pattern:
            fields.append({"path": "", "pattern": pattern, "props": compute_props(text, "string")})
    return TextPathResult(out, fired, fields)


def _scalar(s: str, ctx: ScanContext, recognizers: Sequence[Recognizer], fired: set[PatternId]) -> str:
    result = redact_scalar(s, ctx, recognizers)
    fired.update(result.fired)
    return result.value


# --- JSON ------------------------------------------------------------------------------


def _scan_json(
    text: str,
    recognizers: Sequence[Recognizer],
    fired: set[PatternId],
    fields: list[RedactedField],
) -> str:
    n = len(text)
    stack: list[_Frame] = []

    def top() -> _Frame | None:
        return stack[-1] if stack else None

    def expects_value() -> bool:
        t = top()
        return t is None or t.kind == "arr" or t.state == "value"

    def value_done() -> None:
        t = top()
        if t is not None and t.kind == "obj":
            t.state = "comma"

    def current_path() -> str:
        # RFC 6901 pointer to the value currently being read (object keys from
        # frames, array indices from each array frame's counter).
        parts: list[str] = []
        for f in stack:
            parts.append(f"/{f.index}" if f.kind == "arr" else "/" + escape_pointer_segment(f.key or ""))
        return "".join(parts)

    out: list[str] = []
    i = 0
    while i < n:
        c = text[i]
        if c in _WS:
            out.append(c)
            i += 1
            continue
        if c == "{" or c == "[":
            stack.append(_Frame("obj", "key") if c == "{" else _Frame("arr", "value"))
            out.append(c)
            i += 1
            continue
        if c == "}" or c == "]":
            if stack:
                stack.pop()
            value_done()
            out.append(c)
            i += 1
            continue
        if c == ":" or c == ",":
            t = top()
            if t is not None and t.kind == "obj":
                t.state = "value" if c == ":" else "key"
            if c == "," and t is not None and t.kind == "arr":
                t.index += 1
            out.append(c)
            i += 1
            continue
        if c == '"':
            # Find the closing quote, honouring escapes.
            j = i + 1
            while j < n:
                cj = text[j]
                if cj == "\\":
                    j += 2
                elif cj == '"':
                    break
                else:
                    j += 1
            if j >= n:
                # Unterminated (truncated body): scan the remainder as plain text.
                out.append(_scalar(text[i:], EMPTY_CONTEXT, recognizers, fired))
                i = n
                break
            literal = text[i : j + 1]
            try:
                decoded = json.loads(literal)
                if not isinstance(decoded, str):
                    raise ValueError("not a string literal")
            except ValueError:
                out.append(_scalar(literal, EMPTY_CONTEXT, recognizers, fired))
                i = j + 1
                continue
            t = top()
            is_key = t is not None and t.kind == "obj" and t.state == "key"
            ctx = EMPTY_CONTEXT
            value_path: str | None = None
            if is_key:
                assert t is not None  # implied by is_key; stated for the type checker
                t.key = decoded
                t.state = "colon"
            else:
                if t is not None and t.kind == "obj" and t.key is not None:
                    ctx = ScanContext(key=t.key)
                value_path = current_path()
                value_done()
            redacted = _scalar(decoded, ctx, recognizers, fired)
            if value_path is not None and redacted != decoded:
                pattern = whole_token_id(redacted)
                if pattern:
                    fields.append(
                        {"path": value_path, "pattern": pattern, "props": compute_props(decoded, "string")}
                    )
            out.append(literal if redacted == decoded else encode_json_string(redacted))
            i = j + 1
            continue
        if expects_value() and (c == "-" or is_digit_at(text, i)):
            m = _NUMBER_LITERAL.match(text, i)
            if m is not None:
                lit = m.group(0)
                t = top()
                key = t.key if (t is not None and t.kind == "obj") else None
                pattern = (
                    classify_integer_digits(lit.replace("-", ""), key)
                    if _is_integer_literal(lit)
                    else None
                )
                if pattern:
                    fired.add(pattern)
                    fields.append(
                        {
                            "path": current_path(),
                            "pattern": pattern,
                            "props": compute_props(lit, "number", True),
                        }
                    )
                    out.append(encode_json_string(make_token(pattern)))
                else:
                    out.append(lit)
                value_done()
                i += len(lit)
                continue
        if expects_value():
            keyword = next((w for w in ("true", "false", "null") if text.startswith(w, i)), None)
            if keyword:
                out.append(keyword)
                value_done()
                i += len(keyword)
                continue
        # Residue: anything else, up to the next structural character - scanned as text.
        j = i + 1
        while j < n and text[j] not in _STRUCTURAL:
            j += 1
        out.append(_scalar(text[i:j], EMPTY_CONTEXT, recognizers, fired))
        i = j
    return "".join(out)


def _is_integer_literal(lit: str) -> bool:
    return "." not in lit and "e" not in lit and "E" not in lit


# --- form-urlencoded -------------------------------------------------------------------


def is_form_body(text: str) -> bool:
    """``k=v&k=v...``: no whitespace at all (a real form body encodes spaces as
    ``+``/``%20``), at most one ``=`` per pair, no empty key, and not a lone
    ``blob=`` (a base64 value's padding).
    """
    if "=" not in text or _HAS_WHITESPACE.search(text):
        return False
    pairs = text.split("&")
    for pair in pairs:
        eq = pair.find("=")
        if eq == 0:
            return False
        if eq >= 0 and pair.find("=", eq + 1) >= 0:
            return False
        # A form key never contains a quote (a quoted JSON string body is not a form).
        if '"' in pair[: len(pair) if eq < 0 else eq]:
            return False
    if len(pairs) == 1 and pairs[0].endswith("="):
        return False
    return True


def _scan_form(text: str, recognizers: Sequence[Recognizer], fired: set[PatternId]) -> str:
    out: list[str] = []
    for pair in text.split("&"):
        eq = pair.find("=")
        if eq < 0:
            decoded = form_decode(pair)
            red = _scalar(decoded, EMPTY_CONTEXT, recognizers, fired)
            out.append(pair if red == decoded else form_encode(red))
            continue
        raw_key = pair[:eq]
        raw_val = pair[eq + 1 :]
        key = form_decode(raw_key)
        val = form_decode(raw_val)
        red_key = _scalar(key, EMPTY_CONTEXT, recognizers, fired)
        red_val = _scalar(val, ScanContext(key=key), recognizers, fired)
        out.append(
            (raw_key if red_key == key else form_encode(red_key))
            + "="
            + (raw_val if red_val == val else form_encode(red_val))
        )
    return "&".join(out)


def form_decode(s: str) -> str:
    """``+`` -> space, ``%XX`` -> byte (UTF-8 decoded leniently); malformed escapes pass through."""
    if "%" not in s and "+" not in s:
        return s
    data = bytearray()
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "+":
            data.append(0x20)
        elif c == "%" and _PERCENT_ESCAPE.match(s[i + 1 : i + 3] or ""):
            data.append(int(s[i + 1 : i + 3], 16))
            i += 2
        else:
            data.extend(c.encode("utf-8"))
        i += 1
    return data.decode("utf-8", errors="replace")


def form_encode(s: str) -> str:
    """Minimal re-encoding of a REWRITTEN form key/value.

    Only the characters that would break the ``k=v&k=v`` structure are escaped
    (``%``, ``&``, ``=``, ``+``, CR, LF) and spaces become ``+``; everything else -
    including the token glyphs - is written raw.
    """
    out: list[str] = []
    for c in s:
        if c == " ":
            out.append("+")
        elif c == "%":
            out.append("%25")
        elif c == "&":
            out.append("%26")
        elif c == "=":
            out.append("%3D")
        elif c == "+":
            out.append("%2B")
        elif c == "\r":
            out.append("%0D")
        elif c == "\n":
            out.append("%0A")
        else:
            out.append(c)
    return "".join(out)
