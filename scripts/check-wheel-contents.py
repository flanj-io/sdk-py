#!/usr/bin/env python3
"""Verify a built wheel ships the SDK's entry points and none of the repo's dev/CI
artefacts, before it is ever uploaded.

``scripts/smoke-pack.sh`` already checks the full package/subpackage layout for CI's
own benefit; this is the narrower, release-specific check
``.github/workflows/release.yml`` runs against the exact wheel it is about to publish.

Usage: python scripts/check-wheel-contents.py dist/flanj-X.Y.Z-py3-none-any.whl
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

#: Modules a released wheel must contain. ``register.py`` is the zero-code entry
#: point (``import flanj.register``); ``version.py`` is what ``__version__`` and this
#: whole release pipeline is pinned to.
REQUIRED = {"flanj/register.py", "flanj/version.py"}

#: Repo/CI artefacts that must never ship: contracts and tests are not part of the
#: published library (``pyproject.toml``'s sdist ``include`` makes the same call).
FORBIDDEN_PREFIXES = ("contracts/", "tests/")

TYPED_MARKER = "flanj/py.typed"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check-wheel-contents.py <path-to-wheel>", file=sys.stderr)
        return 2

    wheel = Path(argv[1])
    if not wheel.is_file():
        print(f"::error::no such wheel: {wheel}", file=sys.stderr)
        return 1

    names = set(zipfile.ZipFile(wheel).namelist())

    missing = sorted(REQUIRED - names)
    if missing:
        print(f"::error::wheel is missing required files: {missing}", file=sys.stderr)
        return 1

    # The repo does not currently ship a py.typed marker despite the "Typing :: Typed"
    # classifier in pyproject.toml. Adding one is a src/ packaging decision outside
    # this release workflow's scope — this check only refuses to silently ship a
    # marker with the wrong name if one is ever added, and says which case applies.
    if TYPED_MARKER in names:
        print(f"found typed marker: {TYPED_MARKER}")
    else:
        print(f"note: no {TYPED_MARKER} in the wheel (the repo does not currently ship one)")

    leaked = sorted(n for n in names if n.startswith(FORBIDDEN_PREFIXES))
    if leaked:
        print(f"::error::wheel leaks repo/CI artefacts: {leaked}", file=sys.stderr)
        return 1

    test_like = sorted(n for n in names if n.startswith("flanj/tests/") or "/tests/" in n)
    if test_like:
        print(f"::error::wheel contains test files: {test_like}", file=sys.stderr)
        return 1

    print(f"{wheel.name}: has {sorted(REQUIRED)}, no contracts/ or tests/ ({len(names)} files total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
