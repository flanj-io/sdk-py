# `contracts/` — vendored cross-repo contract (do not hand-edit)

Everything in this directory is a **byte-identical copy** of the canonical contract that lives in
the private `e2e` repo at `e2e/contracts/` (`CONTRACTS.md` + `v1/*`). It is the agreed language
between this SDK and the Flanj collector — the OTLP wire convention the SDK emits and the redaction
floor it must enforce — not test data owned by another repo.

This SDK's suite asserts against these files, so `pytest` proves, standalone, that what this SDK
emits is exactly what the collector expects and that redaction-at-source matches the Go and
TypeScript implementations bit for bit. None of this ships in the published distribution; it is a
repo/CI artifact only.

| File | Role | Asserted by |
|---|---|---|
| `CONTRACTS.md` | the human-readable contract — the public half shared by SDK and collector (§2 OTLP convention and §6 redaction floor are the SDK-relevant sections) | — |
| `golden-otlp-call.json` | the exact OTLP log record the SDK must emit for one HTTP call | *(reference — this SDK does not capture HTTP)* |
| `golden-otlp-mcp-call.json` | the exact OTLP log record for one MCP `tools/call` | `tests/mcp/test_golden_otlp.py` |
| `golden-otlp-mcp-snapshot.json` | the exact `contract_snapshot` record for one complete observed `tools/list` | `tests/mcp/test_golden_otlp.py` |
| `redaction-vectors.json` | scalar/recognizer-level redaction floor vectors | `tests/redaction/test_vectors.py` |
| `redaction-fixtures.json` | the cross-language PARITY battery (Go and TypeScript run the same file) | `tests/redaction/test_fixtures.py`, `test_no_network.py` |

## Changing anything

Edit the canonical file in `e2e/contracts/`, bump `schema_version` if the change is breaking,
re-vendor byte-identically to `sdk/`, `sdk-py/`, `collector/` and `control-plane/`, and make every
repo's suite green. See `e2e/contracts/README.md` (governance) and `REDACTION.md`.
