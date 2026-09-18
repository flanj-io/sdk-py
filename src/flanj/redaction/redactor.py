"""The Flanj redaction floor behind one swappable interface.

Mirrors the Go collector's ``redact.Redactor`` and the TypeScript package's
``Redactor``:

- :meth:`Redactor.redact` recurses ARBITRARY nested structures (dicts, lists,
  scalars) and returns a redacted clone plus the patterns that fired. Every
  string - keys included, undocumented fields included - goes through the
  per-scalar engine; numbers/bools/None are untouched except a PAN-as-number or a
  CVV-under-key, which become string tokens.
- :meth:`Redactor.redact_text` is the production path for captured BODIES: JSON is
  scanned in place (only fired scalars rewritten), forms are decoded-then-scanned,
  anything else is one scalar. Byte-identical to the Go collector and the
  TypeScript package for the same input.

Both report ``fields``: for every WHOLE-VALUE redaction (the scalar became exactly
one token) the RFC 6901 path, the pattern, and the original's non-reversible
properties - so drift detection downstream can still judge type/length of
redacted fields. Span-in-text redactions, redacted keys, form pairs and non-JSON
text emit no fields.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple

from .numbers import classify_integer_digits, integer_digits_of
from .props import RedactedField, compute_props, escape_pointer_segment, sort_fields, whole_token_id
from .recognizer import EMPTY_CONTEXT, Recognizer, ScanContext
from .recognizers import DEFAULT_RECOGNIZERS, OPTIONAL_IP_RECOGNIZER
from .report_order import REPORT_ORDER
from .scalar import redact_scalar
from .text_path import redact_text_path
from .tokens import PatternId, make_token


class RedactValueResult(NamedTuple):
    """Result of the structural entry point."""

    #: A redacted deep clone; the input is never mutated.
    redacted: Any
    #: Which pattern ids fired, in canonical report order (deduped).
    hits: list[PatternId]
    #: Whole-value redactions with the original's captured properties, sorted by path.
    fields: list[RedactedField]


class RedactResult(NamedTuple):
    """Result of the text entry point (the shape the SDK consumes)."""

    #: The redacted text; every sensitive value replaced by a token.
    text: str
    #: Which pattern ids fired, in canonical report order (deduped).
    patterns: list[PatternId]
    #: Whole-value redactions with the original's captured properties, sorted by path.
    fields: list[RedactedField]


class Redactor:
    def __init__(
        self,
        recognizers: Sequence[Recognizer] | None = None,
        include_ip: bool = False,
    ) -> None:
        base: tuple[Recognizer, ...] = (
            DEFAULT_RECOGNIZERS if recognizers is None else tuple(recognizers)
        )
        self._recognizers: Sequence[Recognizer] = (
            base + (OPTIONAL_IP_RECOGNIZER,) if include_ip else base
        )

    def _walk(
        self,
        value: Any,
        ctx: ScanContext,
        path: str,
        fired: set[PatternId],
        fields: list[RedactedField],
    ) -> Any:
        if isinstance(value, str):
            result = redact_scalar(value, ctx, self._recognizers)
            fired.update(result.fired)
            if result.value != value:
                pattern = whole_token_id(result.value)
                if pattern:
                    fields.append(
                        {"path": path, "pattern": pattern, "props": compute_props(value, "string")}
                    )
            return result.value
        # `bool` is a subclass of `int` in Python but is NOT a number here - the
        # TypeScript floor leaves booleans untouched and so must this one.
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            digits = integer_digits_of(value)
            pattern = classify_integer_digits(digits, ctx.key) if digits is not None else None
            if pattern:
                fired.add(pattern)
                fields.append(
                    {
                        "path": path,
                        "pattern": pattern,
                        "props": compute_props(_number_literal(value), "number", True),
                    }
                )
                return make_token(pattern)
            return value
        if isinstance(value, (list, tuple)):
            return [
                self._walk(v, EMPTY_CONTEXT, f"{path}/{i}", fired, fields) for i, v in enumerate(value)
            ]
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                # Redacted KEYS carry no field record - a key is not a
                # spec-addressable value.
                key_text = k if isinstance(k, str) else str(k)
                kr = redact_scalar(key_text, EMPTY_CONTEXT, self._recognizers)
                fired.update(kr.fired)
                out[kr.value] = self._walk(
                    v, ScanContext(key=key_text), f"{path}/{escape_pointer_segment(key_text)}", fired, fields
                )
            return out
        return value  # None and anything else: untouched

    def redact(self, value: Any) -> RedactValueResult:
        fired: set[PatternId] = set()
        fields: list[RedactedField] = []
        redacted = self._walk(value, EMPTY_CONTEXT, "", fired, fields)
        return RedactValueResult(
            redacted=redacted,
            hits=[p for p in REPORT_ORDER if p in fired],
            fields=sort_fields(fields),
        )

    def redact_text(self, text: str) -> RedactResult:
        result = redact_text_path(text, self._recognizers)
        return RedactResult(
            text=result.text,
            patterns=[p for p in REPORT_ORDER if p in result.fired],
            fields=sort_fields(result.fields),
        )


def _number_literal(value: Any) -> str:
    """The number's literal text, as JavaScript's ``String(n)`` would render it."""
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    return str(value)


def create_redactor(
    recognizers: Sequence[Recognizer] | None = None,
    include_ip: bool = False,
) -> Redactor:
    """Build a redactor. The default set is the mandatory floor."""
    return Redactor(recognizers=recognizers, include_ip=include_ip)
