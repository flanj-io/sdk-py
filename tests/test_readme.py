"""The README's public claims, pinned.

`positioning-2026-09.md` (the canonical source for public copy) rules what a README's
first paragraph carries, retired a lead line everywhere on 2026-09-17, and says repos
pin that line's absence. `flanj-io/sdk` pins its README the same way
(`test/readme.spec.ts`).
"""

from __future__ import annotations

from pathlib import Path

README = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
FIRST_SCREEN = README[: README.index("## Quick start")]


def test_the_retired_lead_line_is_absent() -> None:
    """Retired 2026-09-17: REST jargon that does not fit MCP, restating one point three times."""
    for fragment in ("Nothing threw", "Nothing 500'd", "200 OK and a field was renamed"):
        assert fragment not in README, f"the retired lead is back: {fragment!r}"


def test_the_first_paragraph_is_the_headline_and_the_standfirst() -> None:
    assert "Your integration didn't break. It started being wrong." in FIRST_SCREEN
    assert "Every call succeeded. That's why nothing caught it." in FIRST_SCREEN


def test_it_says_early_and_never_claims_supported_for_python() -> None:
    """The promotion rule: *Supported* only once the language's e2e lane is green."""
    assert "Early — MCP only" in FIRST_SCREEN
    assert "Python — **early**" in README
    assert "Python — **supported**" not in README


def test_it_states_what_it_does_not_capture() -> None:
    """Honest limits, stated rather than hidden — a silent gap reads as coverage."""
    assert "**Not captured:**" in README
    assert "HTTP request/response bodies" in README
