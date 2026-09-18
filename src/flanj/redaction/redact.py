"""The default floor: every mandatory recognizer, IP off. Built once per process."""

from __future__ import annotations

from .redactor import Redactor, RedactResult, create_redactor

_default: Redactor | None = None


def _floor() -> Redactor:
    global _default
    if _default is None:
        _default = create_redactor()
    return _default


def redact_detailed(text: str) -> RedactResult:
    """Redact a captured body / free text, returning the text and the fired patterns.

    This is the TEXT entry point of the default floor (see
    :func:`~flanj.redaction.redactor.create_redactor` for the structural entry
    point and custom recognizer sets). Invariants (governed by
    ``contracts/redaction-vectors.json`` + ``contracts/redaction-fixtures.json``):

    - add-only: only replaces sensitive spans, never un-redacts;
    - idempotent: ``redact_detailed(redact_detailed(x).text).text`` is a fixed point;
    - zero I/O: pure function of its input.
    """
    return _floor().redact_text(text)


def redact(text: str) -> str:
    """Redact sensitive values from text. Primary convenience entry point.

    Idempotent and add-only. Safe to run over already-redacted text.
    """
    return redact_detailed(text).text
