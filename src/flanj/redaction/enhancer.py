"""The schema-aware enhancer - our own spec-driven layer ABOVE the floor.

It is applied to the floor's OUTPUT and may only ADD redaction, never subtract:

- it only ever replaces a string/number leaf that carries NO token with a token;
- a scalar the floor already touched is immutable (a poisoned spec cannot relabel
  a PAN as EMAIL, nor "un-redact" anything - there is no operation for it);
- paths that do not resolve are ignored; containers are never replaced.

The never-subtract law - every floor token survives, unchanged, at its path - is
asserted by every language suite over every fixture x every spec.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, NamedTuple

from .redactor import RedactValueResult
from .report_order import REPORT_ORDER
from .tokens import REDACTED_TOKEN_RE, PatternId, make_token

#: One spec-declared sensitive field. ``path`` is dot-separated; a segment may end
#: with ``[]`` to address every element of an array. ``type`` must be a floor
#: pattern id - it names the token emitted; unknown types are ignored.
SensitiveField = dict[str, str]

_KNOWN = frozenset(REPORT_ORDER)


class _Segment(NamedTuple):
    key: str
    arrays: int  # how many trailing `[]`


def _parse_path(path: str) -> list[_Segment] | None:
    if not path:
        return None
    segments: list[_Segment] = []
    for raw in path.split("."):
        key = raw
        arrays = 0
        while key.endswith("[]"):
            key = key[:-2]
            arrays += 1
        if not key:
            return None
        segments.append(_Segment(key, arrays))
    return segments


def _carries_token(value: Any) -> bool:
    """True when a scalar already carries any floor token - such scalars are immutable here."""
    return isinstance(value, str) and REDACTED_TOKEN_RE.search(value) is not None


def enhance(value: Any, spec: Sequence[SensitiveField]) -> RedactValueResult:
    fired: set[PatternId] = set()
    current = value
    for field in spec:
        field_type = field.get("type", "")
        if field_type not in _KNOWN:
            continue
        segments = _parse_path(field.get("path", ""))
        if not segments:
            continue
        current = _apply(current, segments, 0, field_type, fired)
    # The enhancer emits no captured-value fields: it is spec-driven, so the spec
    # already knows the declared shape of every field it redacts.
    return RedactValueResult(
        redacted=current,
        hits=[p for p in REPORT_ORDER if p in fired],
        fields=[],
    )


def _apply_arrays(value: Any, depth: int, leaf: Callable[[Any], Any]) -> Any:
    if depth == 0:
        return leaf(value)
    if not isinstance(value, list):
        return value
    return [_apply_arrays(v, depth - 1, leaf) for v in value]


def _apply(
    value: Any,
    segments: list[_Segment],
    idx: int,
    pattern: PatternId,
    fired: set[PatternId],
) -> Any:
    if idx >= len(segments):
        return value  # unreachable: callers stop at the leaf
    seg = segments[idx]
    if not isinstance(value, dict):
        return value
    if seg.key not in value:
        return value
    is_leaf = idx == len(segments) - 1
    child = value[seg.key]

    def leaf(v: Any) -> Any:
        if is_leaf:
            is_scalar = isinstance(v, str) or (
                isinstance(v, (int, float)) and not isinstance(v, bool)
            )
            if is_scalar and not _carries_token(v):
                fired.add(pattern)
                return make_token(pattern)
            return v
        return _apply(v, segments, idx + 1, pattern, fired)

    replaced = _apply_arrays(child, seg.arrays, leaf)
    if replaced is child:
        return value
    out = dict(value)
    out[seg.key] = replaced
    return out
