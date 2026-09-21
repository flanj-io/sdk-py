"""``scripts/check-release-tag.py``, proved red before it is trusted in CI.

The release workflow's first line of defense: a tag that does not name the version
actually in the tree must fail LOUDLY, before anything is built, let alone uploaded.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from flanj.version import __version__

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check-release-tag.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_the_current_version_tag_passes() -> None:
    result = _run(f"v{__version__}")
    assert result.returncode == 0, result.stderr
    assert __version__ in result.stdout


def test_a_mismatched_tag_fails_loudly() -> None:
    """The exact defect this script exists to catch: a tag that does not name the
    version in src/flanj/version.py. Proved red here before the workflow trusts it.
    """
    wrong = "v0.0.1" if __version__ != "0.0.1" else "v9.9.9"
    result = _run(wrong)
    assert result.returncode != 0
    assert "does not match" in result.stderr
    assert __version__ in result.stderr


def test_a_malformed_tag_is_refused_before_it_is_compared() -> None:
    result = _run("0.1.0")  # missing the leading "v"
    assert result.returncode != 0
    assert "not a vMAJOR.MINOR.PATCH tag" in result.stderr


def test_it_requires_exactly_one_argument() -> None:
    assert _run().returncode == 2
    assert _run("v0.1.0", "extra").returncode == 2
