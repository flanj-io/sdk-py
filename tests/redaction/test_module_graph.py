"""The floor's whole MODULE GRAPH is free of network capability.

``test_import_hygiene.py`` bans the imports we write; this bans the ones our
DEPENDENCIES write. It is the analogue of the Go collector's ``go list -deps``
audit, and it is what backs the claim in REDACTION.md that the composed
validators "have no ``net`` in their trees at all": ``python-stdnum`` does ship
network-backed checks (``stdnum.eu.vat``'s VIES lookup), and this proves the
modules the floor actually imports do not drag them in.

Runs in a FRESH interpreter, because this process has already imported half the
standard library through pytest.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent.parent / "src"

BANNED = [
    "socket",
    "ssl",
    "http",
    "http.client",
    "urllib.request",
    "requests",
    "httpx",
    "aiohttp",
    "zeep",
    "suds",
    "dns",
    "subprocess",
    "multiprocessing",
]

PROBE = """
import sys
import flanj.redaction as floor

# Exercise every validator so nothing lazy is left unimported.
floor.redact('pan 4111111111111111 mail a@b.com iban DE89370400440532013000 tel +14155552671')
floor.create_redactor(include_ip=True).redact({'ip': '10.0.0.1', 'cvv': '123'})

banned = %r
found = sorted(m for m in banned if m in sys.modules)
print(','.join(found))
"""


def test_no_network_module_is_reachable_from_the_floor() -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE % BANNED],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        check=True,
    )
    found = [m for m in result.stdout.strip().split(",") if m]
    assert found == [], (
        "importing and exercising the redaction floor pulled network-capable modules into "
        f"sys.modules: {found}. The floor is a pure function of its input."
    )


def test_the_probe_would_notice() -> None:
    """A probe that cannot see an import proves nothing - prove it sees one."""
    result = subprocess.run(
        [sys.executable, "-c", "import socket\n" + (PROBE % BANNED)],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        check=True,
    )
    assert "socket" in result.stdout
