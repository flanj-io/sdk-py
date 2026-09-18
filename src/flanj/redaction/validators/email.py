"""Email grammar validator - a port of ``validator.isEmail`` (default options).

The TypeScript floor decides with ``validator.isEmail`` and the Go floor with
``govalidator.IsEmail``; both are grammar checks, and this is the same grammar,
so the three agree on the shapes the fixture battery pins. REDACTION.md §3
records the known divergence *class* (different validators may judge exotic
inputs - quoted local parts, unusual TLDs - differently); add a fixture before
relying on any new shape.

Pure function, no I/O, no DNS: deliverability is explicitly NOT checked. An
address that parses is redacted whether or not it resolves - the floor's job is
to stop personal data leaving, not to verify a mailbox.
"""

from __future__ import annotations

import re

_MAX_TOTAL = 254
_MAX_USER = 64
_MAX_DOMAIN = 254
_MAX_LABEL = 63

# validator.js `emailUserUtf8Part` (allow_utf8_local_part defaults to true).
_USER_PART = re.compile("^[a-z\\d!#$%&'*+\\-/=?^_`{|}~¡-￿]+$", re.IGNORECASE)
# validator.js `quotedEmailUserUtf8`.
_QUOTED_USER = re.compile(
    "^([\\s\\x01-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f\\x21\\x23-\\x5b\\x5d-\\x7e¡-￿]"
    "|(\\\\[\\x01-\\x09\\x0b\\x0c\\x0d-\\x7f]))*$",
    re.IGNORECASE,
)
# validator.js `isFQDN` label rule, TLD rule and the full-width guard.
_LABEL = re.compile("^[a-z_¡-￿0-9-]+$", re.IGNORECASE)
_TLD = re.compile("^([a-z¡-¨ª-￿]{2,}|xn[a-z0-9-]{2,})$", re.IGNORECASE)
_FULL_WIDTH = re.compile("[！-～]")
_NUMERIC = re.compile(r"^\d+$")
_WHITESPACE = re.compile(r"\s")


def _byte_len(s: str) -> int:
    return len(s.encode("utf-8"))


def _is_fqdn(domain: str) -> bool:
    """``isFQDN(domain, {require_tld: true})`` - defaults, no underscores, no wildcard."""
    parts = domain.split(".")
    if len(parts) < 2:
        return False
    tld = parts[-1]
    if not _TLD.match(tld):
        return False
    if _WHITESPACE.search(tld):
        return False
    if _NUMERIC.match(tld):
        return False
    for part in parts:
        if len(part) > _MAX_LABEL:
            return False
        if not _LABEL.match(part):
            return False
        if _FULL_WIDTH.search(part):
            return False
        if part.startswith("-") or part.endswith("-"):
            return False
        if "_" in part:  # allow_underscores defaults to false
            return False
    return True


def is_email(value: str) -> bool:
    """True when ``value`` is a syntactically valid email address."""
    if len(value) > _MAX_TOTAL:
        return False
    parts = value.split("@")
    if len(parts) < 2:
        return False
    domain = parts[-1]
    user = "@".join(parts[:-1])
    if _byte_len(user) > _MAX_USER or _byte_len(domain) > _MAX_DOMAIN:
        return False
    if not _is_fqdn(domain):
        return False  # allow_ip_domain defaults to false
    if user.startswith('"'):
        return _QUOTED_USER.match(user[1:-1]) is not None
    for segment in user.split("."):
        if not _USER_PART.match(segment):
            return False
    return True
