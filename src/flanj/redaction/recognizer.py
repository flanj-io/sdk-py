"""The swappable recognizer interface - one shape in every language."""

from __future__ import annotations

from typing import NamedTuple, Protocol

from .tokens import PatternId


class Span(NamedTuple):
    """A half-open ``[start, end)`` span inside a single scalar string."""

    start: int
    end: int


class ScanContext(NamedTuple):
    """Where a scalar sits in its enclosing structure.

    ``key`` is the (original, un-redacted) object key whose value is being
    scanned; ``None`` for keys, array elements, and free text. Only contextual
    recognizers (CVV) use it.
    """

    key: str | None = None


EMPTY_CONTEXT = ScanContext()


class Recognizer(Protocol):
    """One pattern of the floor.

    ``find`` returns the CONFIRMED sensitive spans inside a single scalar string
    - confirmed meaning a hardened validator (Luhn, mod-97, email grammar, phone
    metadata) said yes; our code only LOCATES candidates, it never decides by
    regex.

    Contract for implementations (mirrored by the Go collector and the
    TypeScript package):

    - spans are sorted by ``start`` and non-overlapping;
    - ``find`` is pure and must never perform I/O;
    - the engine behind a recognizer is swappable: replacing one recognizer must
      not touch traversal, token format, base64 or gating.
    """

    @property
    def id(self) -> PatternId: ...

    def find(self, value: str, ctx: ScanContext) -> list[Span]: ...
