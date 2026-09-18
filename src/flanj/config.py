"""Capture gating: the body cap and the content-type allowlist (CONTRACTS section 2)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

#: Default body capture cap in bytes (contract key ``body_cap_bytes``).
DEFAULT_BODY_CAP_BYTES: Final = 16384

#: Content-type prefixes eligible for body capture. Each entry is matched as a
#: prefix of the MEDIA TYPE alone - ``type/subtype``, lowercased, parameters such
#: as ``; charset=utf-8`` stripped - so ``text/`` admits every ``text/*`` and
#: ``application/json`` admits ``application/json; charset=utf-8``.
#:
#: A media type carrying an RFC 6839 structured suffix is ALSO matched by the base
#: type that suffix denotes: ``application/problem+json`` (RFC 7807),
#: ``application/vnd.api+json``, ``application/hal+json``, ... all capture because
#: ``application/json`` is listed.
DEFAULT_CAPTURE_CONTENT_TYPES: Final[Sequence[str]] = (
    "application/json",
    "application/x-www-form-urlencoded",
    "text/",
)

#: RFC 6839 structured-syntax suffixes and the base media type each denotes.
_STRUCTURED_SUFFIX_BASE: Final[dict[str, str]] = {"json": "application/json"}


def _parse_media_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    semicolon = content_type.find(";")
    media = (content_type if semicolon < 0 else content_type[:semicolon]).strip().lower()
    return media or None


def _structured_base_of(media_type: str) -> str | None:
    plus = media_type.rfind("+")
    if plus < 0:
        return None
    return _STRUCTURED_SUFFIX_BASE.get(media_type[plus + 1 :])


def is_captureable_content_type(
    content_type: str | None,
    allowed: Sequence[str] = DEFAULT_CAPTURE_CONTENT_TYPES,
) -> bool:
    """True when a content-type header value is eligible for body capture."""
    media_type = _parse_media_type(content_type)
    if media_type is None:
        return False
    base = _structured_base_of(media_type)
    for entry in allowed:
        prefix = entry.strip().lower()
        if not prefix:
            continue
        if media_type.startswith(prefix) or (base is not None and base.startswith(prefix)):
            return True
    return False


def cap_text(text: str, cap: int = DEFAULT_BODY_CAP_BYTES) -> tuple[str, bool]:
    """Apply the byte cap the HTTP path applies to its raw buffers.

    The cap is in BYTES, not characters, because the OTLP attribute budget is bytes.
    """
    if not text:
        return text, False
    raw = text.encode("utf-8")
    if len(raw) <= cap:
        return text, False
    # A multi-byte character split by the cap decodes to U+FFFD, which is what
    # Node's `Buffer.toString('utf8')` produces for the same truncated bytes - the
    # capped text has to be the same string in both SDKs.
    return raw[:cap].decode("utf-8", errors="replace"), True
