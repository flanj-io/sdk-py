"""Shared fixture loading for the contract suites.

``contracts/`` is a byte-identical vendored copy of the canonical contract.
The files - not this implementation - are the contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"


def load(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


VECTORS = load("redaction-vectors.json")
FIXTURES = load("redaction-fixtures.json")


def js_json(value: Any) -> str:
    """Serialize exactly as JavaScript's ``JSON.stringify`` does.

    The parity oracle runs the text path over ``JSON.stringify(case.input)``, so
    this has to agree byte for byte: no whitespace, and non-ASCII written raw
    rather than ``\\u``-escaped.
    """
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
