"""IP validator - the :mod:`ipaddress` standard library.

Matches ``validator.isIP`` on the shapes that matter: leading zeros are rejected
(CPython 3.9.5+), as are out-of-range octets. Pure function, no I/O - nothing
here resolves a name.
"""

from __future__ import annotations

import ipaddress


def is_ip(value: str, version: int) -> bool:
    try:
        if version == 4:
            ipaddress.IPv4Address(value)
        else:
            ipaddress.IPv6Address(value)
    except ValueError:
        return False
    return True
