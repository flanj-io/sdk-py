"""THE security floor conformance suite.

The vector file - not this code - is the contract. Every case (positives,
negatives, idempotency, multi) must pass, and the idempotency + add-only
invariants are enforced across the whole set.
"""

from __future__ import annotations

import pytest

from flanj.redaction import redact, redact_detailed

from ..conftest import VECTORS

CASES = VECTORS["cases"]
IDS = [c["id"] for c in CASES]


def test_loads_the_vendored_golden_vector_file() -> None:
    assert len(CASES) > 0


@pytest.mark.parametrize("vector", CASES, ids=IDS)
def test_produces_the_expected_redacted_text(vector: dict) -> None:
    assert redact(vector["input"]) == vector["expected"]


@pytest.mark.parametrize("vector", CASES, ids=IDS)
def test_reports_the_expected_fired_patterns(vector: dict) -> None:
    assert redact_detailed(vector["input"]).patterns == vector["patterns"]


@pytest.mark.parametrize("vector", CASES, ids=IDS)
def test_is_idempotent(vector: dict) -> None:
    once = redact(vector["input"])
    assert redact(once) == once


@pytest.mark.parametrize("vector", CASES, ids=IDS)
def test_re_redacting_the_expected_output_is_inert(vector: dict) -> None:
    # The golden expected output must be a fixed point of redaction.
    assert redact(vector["expected"]) == vector["expected"]


def test_never_un_redacts_an_emitted_token() -> None:
    text = '{"source":"⟦REDACTED:PAN⟧","email":"⟦REDACTED:EMAIL⟧"}'
    assert redact(text) == text
    assert redact_detailed(text).patterns == []


def test_idempotent_for_a_body_carrying_many_pii_types_at_once() -> None:
    text = (
        "pan 4111111111111111 mail a@b.com iban DE89370400440532013000 "
        "ssn 123-45-6789 tel +14155552671"
    )
    once = redact(text)
    assert redact(once) == once
    assert "4111111111111111" not in once
    assert "a@b.com" not in once
