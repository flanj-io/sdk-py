"""The README's public claims, pinned.

The retired lead line must not appear anywhere in the README, and the first
paragraph must carry the current headline and standfirst. `flanj-io/sdk` pins
its README the same way (`test/readme.spec.ts`).
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
    """The promotion rule: *Supported* only once the language's end-to-end integration suite is green."""
    assert "Early — MCP only" in FIRST_SCREEN
    assert "Python — **early**" in README
    assert "Python — **supported**" not in README


def test_it_states_what_it_does_not_capture() -> None:
    """Honest limits, stated rather than hidden — a silent gap reads as coverage."""
    assert "**Not captured:**" in README
    assert "HTTP request/response bodies" in README


def test_the_quick_start_leads_with_the_zero_code_entry_and_the_load_first_rule() -> None:
    """Loading flanj after the app imports an MCP transport opener silently loses edge
    detection - the README's own smoke script got it wrong the day the rule was new."""
    quick_start = README[README.index("## Quick start") : README.index("## What is captured")]
    assert "import flanj.register" in quick_start
    assert "### Load flanj first" in quick_start
    assert "`unknown`" in quick_start, "the README must say what happens when the rule is broken"
