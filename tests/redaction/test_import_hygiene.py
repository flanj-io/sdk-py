"""Static zero-I/O ban over the redaction floor's source.

The TypeScript package enforces this with an ESLint ``no-restricted-imports`` rule
over ``packages/redaction-patterns/src/**``; the Go collector enforces it with a
source ban plus a ``go list -deps`` audit. This is the Python equivalent: walk the
AST of every module under ``flanj/redaction/`` and fail on any import that could
reach the network, the filesystem or a subprocess.

It is deliberately static and deliberately crude. The runtime sentinel in
``test_no_network.py`` proves the battery makes no calls; this proves the capability
is not even in the module graph, which is the part a future contributor is most
likely to regress by reaching for a convenient helper.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

FLOOR = Path(__file__).resolve().parent.parent.parent / "src" / "flanj" / "redaction"

BANNED_ROOTS: set[str] = {
    # network / DNS
    "socket",
    "ssl",
    "asyncio",
    "http",
    "urllib",
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
    "telnetlib",
    "xmlrpc",
    "webbrowser",
    "dns",
    "dnspython",
    # process / environment
    "subprocess",
    "os",
    "multiprocessing",
    "signal",
    # filesystem
    "pathlib",
    "shutil",
    "tempfile",
    "io",
    "glob",
    "fileinput",
    "sqlite3",
    # import machinery that could fetch any of the above at runtime
    "importlib",
    "ctypes",
}


def _modules() -> Iterator[Path]:
    yield from sorted(FLOOR.rglob("*.py"))


def _imports(tree: ast.AST) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: inside the floor, by definition
                continue
            if node.module:
                yield node.module, node.lineno


def test_the_floor_is_not_empty() -> None:
    assert len(list(_modules())) > 15


@pytest.mark.parametrize("path", list(_modules()), ids=lambda p: str(p.name))
def test_module_imports_nothing_that_can_do_io(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    for module, lineno in _imports(tree):
        root = module.split(".")[0]
        if root in BANNED_ROOTS:
            offenders.append(f"{path.name}:{lineno} imports {module}")
    assert offenders == [], (
        "the redaction floor must do no I/O, so it may not import a network, filesystem or "
        "subprocess primitive: " + "; ".join(offenders)
    )


def test_the_ban_would_catch_a_real_regression() -> None:
    """A ban that matches nothing proves nothing - prove it matches."""
    tree = ast.parse("import socket\nfrom urllib.request import urlopen\nfrom . import tokens\n")
    roots = {m.split(".")[0] for m, _ in _imports(tree)}
    assert "socket" in roots and "urllib" in roots
    assert roots & BANNED_ROOTS == {"socket", "urllib"}
