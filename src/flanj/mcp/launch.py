"""``flanj.mcp.server.command`` - how a stdio MCP server was launched.

A stdio server's identity is the name it reports about itself (``serverInfo.name``),
so a vendor's ``npx @stripe/mcp`` and a third party's ``npx someone/stripe-mcp``
look alike on the collector. The launch command says which package is actually
behind it. The collector shows it on the contract card; it is never part of a flag.

The encoding is specified to the byte in CONTRACTS section 2, because the TypeScript
SDK must emit the identical string for the same command:

- a compact JSON array ``[command, ...args]`` (no whitespace, non-ASCII raw);
- each element floor-redacted ON ITS OWN with the text entry point;
- capped at 1024 UTF-8 bytes: elements are kept in order while the array plus a
  closing ``"…"`` still fits, and the last element is exactly ``"…"`` whenever one
  was dropped; the command itself is always kept, and if even ``[command, "…"]``
  does not fit, there is no attribute at all.

Never the environment or the working directory: those carry credentials.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from ..redaction import redact

#: The cap on the serialized array, in UTF-8 bytes (CONTRACTS section 2).
MAX_COMMAND_BYTES = 1024
#: The element that marks dropped arguments: U+2026 HORIZONTAL ELLIPSIS.
ELLIPSIS = "…"


def _encode(elements: Sequence[str]) -> str:
    return json.dumps(list(elements), ensure_ascii=False, separators=(",", ":"))


def _fits(text: str) -> bool:
    return len(text.encode("utf-8")) <= MAX_COMMAND_BYTES


def launch_command_attribute(command: str, args: Sequence[str] = ()) -> str | None:
    """The attribute value for a stdio launch, or None when it cannot be carried."""
    if not isinstance(command, str) or not command:
        return None
    elements = [redact(command)] + [redact(str(a)) for a in args]
    full = _encode(elements)
    if _fits(full):
        return full
    kept = [elements[0]]
    for element in elements[1:]:
        if _fits(_encode([*kept, element, ELLIPSIS])):
            kept.append(element)
        else:
            break
    capped = _encode([*kept, ELLIPSIS])
    return capped if _fits(capped) else None
