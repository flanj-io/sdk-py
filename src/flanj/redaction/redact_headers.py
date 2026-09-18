"""Header allowlist + redaction (CONTRACTS section 2)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .redact import redact
from .tokens import make_token

#: Default header allowlist. Every other header key is DROPPED - not redacted,
#: not emitted. Keys are matched case-insensitively.
DEFAULT_HEADER_ALLOWLIST: Sequence[str] = (
    "content-type",
    "content-length",
    "content-encoding",
    "x-request-id",
    "x-correlation-id",
    "idempotency-key",
    "user-agent",
    "date",
)

#: Credential-bearing headers. If one is ever seen in an allowlisted context it is
#: emitted as a token, never raw. They are NOT in the default allowlist, so by
#: default they are dropped entirely.
_SENSITIVE_HEADERS = frozenset(("authorization", "cookie", "set-cookie"))


def redact_headers(
    headers: Mapping[str, Any] | None,
    allowlist: Sequence[str] = DEFAULT_HEADER_ALLOWLIST,
) -> dict[str, str]:
    """Produce a redacted, allowlisted header map suitable for storage/emission.

    - keys not in ``allowlist`` (case-insensitive) are dropped;
    - credential headers are forced to a TOKEN token if allowlisted;
    - surviving values are run through :func:`redact` as defense-in-depth.
    """
    out: dict[str, str] = {}
    if not headers:
        return out
    allow = {k.lower() for k in allowlist}
    for raw_key, raw_value in headers.items():
        key = raw_key.lower()
        if key not in allow:
            continue
        if raw_value is None:
            continue
        if key in _SENSITIVE_HEADERS:
            out[key] = make_token("TOKEN")
            continue
        if isinstance(raw_value, (list, tuple)):
            value = ", ".join(str(v) for v in raw_value)
        else:
            value = str(raw_value)
        out[key] = redact(value)
    return out
