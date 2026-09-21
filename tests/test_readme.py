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


def test_the_shared_cross_language_skeleton() -> None:
    """The two SDKs' READMEs are built on ONE skeleton: the same sections in the
    same order, differing only where the language or the HTTP half forces it.

    They had drifted into two unrelated documents describing what is very nearly
    the same product, which is how a reader concludes the SDKs differ far more
    than they do. Each repo can only pin its own half; this is the Python half.
    Adding, removing or reordering a section here means doing the same in
    ``flanj-io/sdk``'s README (its ``test/readme.spec.ts`` pins the twin).
    """
    headings = [
        line.lstrip("#").strip() for line in README.splitlines() if line.startswith(("# ", "## ", "### "))
    ]
    assert headings == [
        "flanj — Flanj SDK for Python",
        "Quick start",
        "On Kubernetes",
        "Load flanj first",  # language-specific: the TypeScript README has "ESM, CJS, and shutdown" here
        "MCP quick start",
        "Instrumenting a client yourself",
        "Configuration",
        # The TypeScript README has "Running next to OpenTelemetry" here — HTTP-only, no counterpart.
        "What is captured",
        "MCP clients: the contract arrives with the traffic",
        "It stays out of the way",
        # The TypeScript README has "Also in this distribution" here — its second published package.
        "Status",
        "Development",
        "Security",
        "License",
    ]


def test_the_mcp_quick_start_states_what_a_call_records() -> None:
    """The same facts, in the same section, as the TypeScript README's MCP quick start."""
    start = README.index("### MCP quick start")
    section = README[start : README.index("### Instrumenting a client yourself")]
    for fact in (
        "structuredContent",
        "isError",
        "_meta",
        "client-generated",
        "tasks/get",
        "refetch_on_list_changed",
        "npx @stripe/mcp@0.2.1",
    ):
        assert fact in section, f"the MCP quick start does not mention {fact}"
    assert "never sent to the control plane" in section


def test_it_documents_the_capture_failure_warning() -> None:
    assert "FLANJ_SILENCE_CAPTURE_WARNINGS" in README
    assert "your application is unaffected" in README.lower()
