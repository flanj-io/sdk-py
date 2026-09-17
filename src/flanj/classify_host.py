"""SDK edge classification of a peer host (CONTRACTS section 2 ``flanj.edge.class``).

Classify a peer host as ``internal`` or ``external`` per the heuristic shared,
BYTE-FOR-BYTE, by every Flanj component (SDK egress/ingress + collector).

A host is **internal** if it is RFC1918 (``10/8``, ``172.16-31/12``,
``192.168/16``), loopback (``127/8``, ``::1``, ``localhost``), unspecified (``::``),
link-local (``169.254/16``, ``fe80::/10``), a unique-local IPv6 address
(``fc00::/7``), a single-label hostname, or carries an internal name suffix.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

EdgeClass = str  # 'external' | 'internal'

_INTERNAL_NAME_SUFFIXES: Sequence[str] = (".svc.cluster.local", ".internal", ".local")
_IPV4_SHAPE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_MAPPED_IPV4 = re.compile(r"^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$")


def classify_host(host: str) -> EdgeClass:
    hostname = _normalize_hostname(host)
    if not hostname:
        return "internal"
    if ":" in hostname:
        return _classify_ipv6(hostname)
    if _IPV4_SHAPE.match(hostname):
        return _classify_ipv4(hostname)
    return _classify_name(hostname)


def _normalize_hostname(host: str) -> str:
    """Strip brackets, an IPv6-mapped-IPv4 prefix, and a trailing ``:port``; lowercase."""
    h = host.strip().lower()
    if not h:
        return ""
    if h.startswith("["):
        end = h.find("]")
        return _unmap_ipv4(h[1:end] if end != -1 else h[1:])
    # Exactly one colon => host:port (IPv4 or name). More than one => bare IPv6.
    if h.count(":") == 1:
        h = h[: h.find(":")]
    return _unmap_ipv4(h)


def _unmap_ipv4(h: str) -> str:
    m = _MAPPED_IPV4.match(h)
    return m.group(1) if m else h


def _classify_ipv6(h: str) -> EdgeClass:
    if h == "::1" or h == "::":
        return "internal"  # loopback / unspecified
    if re.match(r"^f[cd]", h):
        return "internal"  # ULA fc00::/7
    if re.match(r"^fe[89ab]", h):
        return "internal"  # link-local fe80::/10
    return "external"


def _classify_ipv4(h: str) -> EdgeClass:
    parts = h.split(".")
    try:
        a = int(parts[0])
        b = int(parts[1])
    except (IndexError, ValueError):
        return "external"
    if a == 127:
        return "internal"  # loopback 127/8
    if a == 10:
        return "internal"  # RFC1918 10/8
    if a == 192 and b == 168:
        return "internal"  # RFC1918 192.168/16
    if a == 172 and 16 <= b <= 31:
        return "internal"  # RFC1918 172.16-31/12
    if a == 169 and b == 254:
        return "internal"  # link-local 169.254/16
    return "external"


def _classify_name(h: str) -> EdgeClass:
    if h == "localhost":
        return "internal"
    if any(h.endswith(s) for s in _INTERNAL_NAME_SUFFIXES):
        return "internal"
    if "." not in h:
        return "internal"  # single-label hostname
    return "external"
