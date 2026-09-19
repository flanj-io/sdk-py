"""THE cross-language PARITY suite.

``contracts/redaction-fixtures.json`` (vendored from the canonical
contract source) is run by this suite AND by the TypeScript package's and the
Go collector's; all three must produce these exact results. This file is the
contract, not the code.

- kind=json: BOTH entry points are asserted - the structural ``redact(value)`` and
  the text path over the serialized body, parsed back - by deep equality (the
  parity oracle).
- kind=text: the text path must match byte-for-byte.
- every case must be idempotent (redacting ``expected`` is a no-op that fires
  nothing).
- ``enhancer`` cases run the schema-aware enhancer on the floor's output; and the
  never-subtract law is asserted over the cross product of every json case x every
  spec in the file.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from flanj.redaction import REDACTED_TOKEN_RE, create_redactor, enhance, redact_detailed

from ..conftest import FIXTURES, js_json

CASES: list[dict[str, Any]] = FIXTURES["cases"]
IDS = [c["id"] for c in CASES]
JSON_CASES = [c for c in CASES if c["kind"] == "json"]
JSON_IDS = [c["id"] for c in JSON_CASES]

redactor = create_redactor()


def tokens_by_path(
    value: Any, path: str = "$", out: dict[str, list[str]] | None = None
) -> dict[str, list[str]]:
    """Every token in a value, keyed by its JSON path - the never-subtract oracle."""
    if out is None:
        out = {}
    if isinstance(value, str):
        found = REDACTED_TOKEN_RE.findall(value)
        if found:
            out[path] = found
    elif isinstance(value, list):
        for i, v in enumerate(value):
            tokens_by_path(v, f"{path}[{i}]", out)
    elif isinstance(value, dict):
        for k, v in value.items():
            key_tokens = REDACTED_TOKEN_RE.findall(k)
            if key_tokens:
                out[f"{path}.<key:{k}>"] = key_tokens
            tokens_by_path(v, f"{path}.{k}", out)
    return out


def test_loads_the_vendored_fixture_file() -> None:
    assert len(CASES) > 50


@pytest.mark.parametrize("case", JSON_CASES, ids=JSON_IDS)
def test_structural_redact_deep_equals_expected(case: dict) -> None:
    result = redactor.redact(case["input"])
    assert result.redacted == case["expected"]
    assert result.hits == case["patterns"]
    assert result.fields == case.get("fields", [])


@pytest.mark.parametrize("case", JSON_CASES, ids=JSON_IDS)
def test_text_path_parses_back_to_expected(case: dict) -> None:
    result = redactor.redact_text(js_json(case["input"]))
    assert json.loads(result.text) == case["expected"]
    assert result.patterns == case["patterns"]
    assert result.fields == case.get("fields", [])


@pytest.mark.parametrize("case", JSON_CASES, ids=JSON_IDS)
def test_structural_path_is_idempotent_and_emits_no_fields_again(case: dict) -> None:
    again = redactor.redact(case["expected"])
    assert again.redacted == case["expected"]
    assert again.hits == []
    assert again.fields == []


@pytest.mark.parametrize("case", JSON_CASES, ids=JSON_IDS)
def test_never_mutates_its_input(case: dict) -> None:
    frozen = js_json(case["input"])
    redactor.redact(case["input"])
    assert js_json(case["input"]) == frozen


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["kind"] == "text"], ids=[c["id"] for c in CASES if c["kind"] == "text"]
)
def test_text_path_matches_byte_for_byte(case: dict) -> None:
    result = redactor.redact_text(case["input"])
    assert result.text == case["expected"]
    assert result.patterns == case["patterns"]
    assert result.fields == case.get("fields", [])
    # The module-level entry point agrees.
    assert redact_detailed(case["input"]).text == case["expected"]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_is_idempotent_on_the_text_path(case: dict) -> None:
    expected_text = js_json(case["expected"]) if case["kind"] == "json" else case["expected"]
    again = redactor.redact_text(expected_text)
    assert again.text == expected_text
    assert again.patterns == []


ENHANCER_CASES = [c for c in CASES if c.get("enhancer")]


@pytest.mark.parametrize("case", ENHANCER_CASES, ids=[c["id"] for c in ENHANCER_CASES])
def test_schema_aware_enhancer_produces_the_expected_value(case: dict) -> None:
    floor = redactor.redact(case["input"])
    enhanced = enhance(floor.redacted, case["enhancer"]["spec"])
    assert enhanced.redacted == case["enhancer"]["expected"]
    assert enhanced.hits == case["enhancer"]["patterns"]


#: Every spec in the file, plus a HOSTILE one that points at every floor-redacted
#: field with a different type.
SPECS: list[list[dict[str, str]]] = [[]] + [c["enhancer"]["spec"] for c in ENHANCER_CASES]
SPECS.append(
    [
        {"path": "card_number", "type": "EMAIL"},
        {"path": "card", "type": "IP"},
        {"path": "cards[]", "type": "TOKEN"},
        {"path": "items[].pan", "type": "SSN"},
        {"path": "charge.source.card_number", "type": "PHONE"},
        {"path": "payment.card.number", "type": "EMAIL"},
    ]
)


@pytest.mark.parametrize("case", JSON_CASES, ids=JSON_IDS)
def test_never_subtract_law(case: dict) -> None:
    """enhancer(floor(x), spec) is a superset of floor(x) for every json case x every spec."""
    floor = redactor.redact(case["input"])
    before = tokens_by_path(floor.redacted)
    for spec in SPECS:
        after = tokens_by_path(enhance(floor.redacted, spec).redacted)
        for path, toks in before.items():
            assert after.get(path) == toks, f"spec {spec} removed/changed tokens at {path}"
