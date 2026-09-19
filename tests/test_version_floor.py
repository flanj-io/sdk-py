"""The supported-Python floor is stated in three places; each pair is locked here.

The TypeScript SDK keeps the identical triad for Node - ``engines.node``, the
README's Quick start line, and ``SUPPORTED_NODE_RANGE`` - with a test on each pair,
because the failure mode is silent and asymmetric: a ``requires-python`` that drifts
above the code's gate makes pip refuse a runtime that would have worked, and one that
drifts below installs cleanly onto a runtime the code then refuses at import.

Change all three or none.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from flanj.runtime import (
    SUPPORTED_PYTHON,
    SUPPORTED_PYTHON_SPECIFIER,
    assert_supported_python,
    is_supported_python,
    supported_python_display,
)

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_pyproject_requires_python_matches_the_constant() -> None:
    m = re.search(r'^requires-python\s*=\s*"([^"]+)"', PYPROJECT, re.MULTILINE)
    assert m is not None, "pyproject.toml has no requires-python"
    assert m.group(1) == SUPPORTED_PYTHON_SPECIFIER


def test_readme_requirements_line_matches_the_constant() -> None:
    assert re.search(
        rf"\*\*Python {re.escape(supported_python_display())}\+\*\*", README
    ), f"the README must state the floor as **Python {supported_python_display()}+**"


def test_pyproject_classifiers_start_at_the_floor() -> None:
    """A classifier below the floor advertises a runtime the code refuses."""
    versions = re.findall(r'"Programming Language :: Python :: (\d+)\.(\d+)"', PYPROJECT)
    assert versions, "no per-version classifiers found"
    lowest = min((int(a), int(b)) for a, b in versions)
    assert lowest == SUPPORTED_PYTHON


def test_the_gate_accepts_the_runtime_running_this_suite() -> None:
    assert is_supported_python()
    assert_supported_python()  # must not raise


def test_the_gate_refuses_below_the_floor_with_one_sentence(monkeypatch: pytest.MonkeyPatch) -> None:
    below = (SUPPORTED_PYTHON[0], SUPPORTED_PYTHON[1] - 1, 0)
    monkeypatch.setattr(sys, "version_info", below + (0, "final", 0))

    assert not is_supported_python()
    with pytest.raises(RuntimeError) as excinfo:
        assert_supported_python()

    message = str(excinfo.value)
    assert message.count(".") >= 1
    assert SUPPORTED_PYTHON_SPECIFIER in message, "the refusal must name the floor"
    assert ".".join(str(p) for p in below) in message, "the refusal must name the runtime in hand"
    assert message.count(". ") <= 1 and message.endswith("."), (
        "the refusal is ONE sentence - a wall of text at import time is what people paste "
        "into an issue instead of reading"
    )


def test_instrumenting_on_an_unsupported_runtime_refuses_before_it_wraps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate has to run at instrumentation time, not just be importable: a session
    that got silently half-wrapped on an unsupported runtime is the worse failure.
    """
    from flanj.mcp import instrument_mcp_client

    class Session:
        async def call_tool(self, name: str, arguments: object = None) -> object:
            return None

    session = Session()
    monkeypatch.setattr(sys, "version_info", (SUPPORTED_PYTHON[0], SUPPORTED_PYTHON[1] - 1, 0, "final", 0))

    with pytest.raises(RuntimeError):
        instrument_mcp_client(session)

    # Identity comparison would not work here: attribute access on a bound method
    # builds a fresh object every time. What the wrapper actually does is SHADOW the
    # class method with an instance attribute, so the check is that no such
    # attribute was installed - and that no instrumented marker was left behind
    # either, which would make a later, legitimate call a silent no-op.
    assert "call_tool" not in vars(session), "the session must be left unwrapped"
    assert not getattr(session, "__flanj_mcp_instrumented__", False)
