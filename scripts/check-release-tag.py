#!/usr/bin/env python3
"""Verify a release tag matches ``src/flanj/version.py`` — fail loudly if not.

The first line of defense in ``.github/workflows/release.yml``: a tag that does not
name the version actually in the tree must never reach a build, let alone an upload.

Self-tested (``tests/test_check_release_tag.py``): proved red against a deliberately
mismatched tag before it was trusted in CI.

Usage: python scripts/check-release-tag.py vX.Y.Z
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "src" / "flanj" / "version.py"

TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
VERSION_ASSIGNMENT_RE = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE)


def package_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = VERSION_ASSIGNMENT_RE.search(text)
    if match is None:
        raise SystemExit(f"::error::could not find __version__ in {VERSION_FILE}")
    return match.group(1)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check-release-tag.py vX.Y.Z", file=sys.stderr)
        return 2

    tag = argv[1]
    if not TAG_RE.fullmatch(tag):
        print(f"::error::'{tag}' is not a vMAJOR.MINOR.PATCH tag", file=sys.stderr)
        return 1

    version = package_version()
    want = f"v{version}"
    if tag != want:
        print(
            f"::error::tag {tag!r} does not match src/flanj/version.py's "
            f"__version__ {version!r} (expected {want!r})",
            file=sys.stderr,
        )
        return 1

    print(f"tag {tag} matches src/flanj/version.py ({version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
