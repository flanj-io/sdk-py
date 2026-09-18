# CLAUDE.md — `flanj` (Python SDK)

Guidance for Claude Code (and engineers) working in this repo.

## What this repo is

The **Flanj SDK for Python**: out-of-band capture of **MCP client** traffic with
**redaction-at-source**, exported as one OTLP log record per call to the collector. It is the first
step of the pipeline (**capture** → detect → surface → flag → peek). Public, **Apache-2.0** — keep it
pristine (legal and compliance teams at regulated organizations read it; no copyleft or
source-available dependencies, prefer Apache/MIT/BSD/ISC/PSF).

**MCP only, and that is the product, not a stage of one.** There is no HTTP body capture here:
Python has no `node:http` choke point to patch the way the TypeScript SDK does, and an agent
application has MCP traffic to watch rather than a REST integration. Do not add HTTP capture without
a ruling — it is a scope decision, not an implementation gap.

Everything public says **Early — MCP only**, never *Supported*, until the `org-app-py` lane is green
in the `e2e` harness (the promotion rule in `docs/mvp-roadmap.md`).

## Role in the system

`agent → (flanj captures + redacts) → OTLP/HTTP :4318 → collector`. The collector compares what a
server returned against what its `tools/list` said it would return. Bodies are the non-redundant
evidence; redaction happens **here**, at the call site, before anything is attached or exported.

## Stack & commands

- Python **>= 3.10** — the published `requires-python`, and a real floor: it is the floor of the
  official `mcp` package this SDK instruments. Three places state it and a test locks each
  (`pyproject.toml` `requires-python`, the README's Requirements line, `SUPPORTED_PYTHON` in
  `flanj/runtime.py`). **Change all three or none.** `tests/test_version_floor.py`.
- `uv venv --python 3.10 && uv pip install -e ".[dev]"` · `pytest` · `ruff check .` · `mypy` ·
  `bash scripts/smoke-pack.sh`.
- Runtime dependencies are deliberately few: `phonenumbers` (the phone validator) and the
  OpenTelemetry logs export path. `mcp` is a **dev** dependency only — it is feature-detected at
  runtime, never imported.

## Layout

```
src/flanj/
  __init__.py              # LAZY exports (PEP 562) — see "Two traps" below
  version.py               # __version__ (plain assignment: the build backend regexes it)
  runtime.py               # the Python floor + the one-sentence refusal
  config.py                # body cap + content-type gate
  classify_host.py         # external | internal edge heuristic (byte-identical in the collector)
  captured_call.py         # the redacted hand-off shape
  assemble_call.py         # the direction-agnostic redact-at-source assembler
  otlp_record.py           # build the flanj.* OTLP attributes from a CapturedCall
  otlp_endpoint.py         # FLANJ_/OTEL_ precedence + base-URL -> /v1/logs normalization
  otlp.py                  # the convenience logger
  mcp/
    instrument.py          # instrument_mcp_client — THE async contract lives here
    result_meta.py         # the `_meta` readers for protocol revision 2026-07-28
    assemble_call.py       # tools/call -> CapturedCall via the shared assembler
    assemble_snapshot.py   # complete tools/list -> floor-redacted ToolDef-shaped snapshot
    resolve_edge.py, record.py, types.py
  redaction/               # the floor — ZERO I/O. See REDACTION.md.
    validators/            # the hardened validators that DECIDE (email, iban, phone, ip)
    recognizers/           # the locators (pan, email, iban, phone, ssn, cvv, token, ip)
    scalar.py, text_path.py, redactor.py, enhancer.py, props.py, base64_scan.py, ...
contracts/                 # vendored from the canonical e2e/contracts (do not hand-edit)
scripts/smoke-pack.sh      # a stranger's first run: build -> fresh venv -> real MCP server
docs/CONCEPTS.md           # the public engineering overview (mirrors flanj-io/sdk's)
src/flanj/mcp/CLAUDE.md    # the MCP instrumentation, file by file, with each TypeScript twin
tests/test_readme.py       # pins the README's public claims (positioning-2026-09.md)
.github/                   # CODEOWNERS, CI, issue/PR templates, dependabot — mirror flanj-io/sdk's
```

## Non-negotiables (do not regress)

1. **Redact before attach/export.** Assemble, redact, keep only the redacted string. A raw body must
   never be set as an attribute — not even transiently.
2. **The async contract.** `call_tool` is a coroutine. Capture must not change timing, must not
   swallow `CancelledError`, and must not alter how a result behaves. `except Exception` — **never**
   `except BaseException`; add no `await` beyond the wrapped one; read the result, never iterate it.
   `tests/mcp/test_async_transparency.py` locks all three, and each test was proved red against the
   defect it guards. This is the bug class that shipped once already in the other runtime.
3. **Caps & gating.** Content-type gate (JSON/text/form only); 16 KiB body cap; an internal edge is
   metadata-only. A Tasks handle records the envelope with **no** body.
4. **Emit the exact `flanj.*` convention** in `contracts/CONTRACTS.md` §2. The emitted records must
   match `contracts/golden-otlp-mcp-call.json` and `-snapshot.json` — asserted on the FULL attribute
   map, both directions, so an *extra* attribute fails too.
5. **The floor does no I/O**, and that is checked three ways (sentinel, static import ban,
   module-graph audit). It is why the floor owns its Luhn and IBAN checks and why
   `flanj/__init__.py` is lazy.

## Contract

Wire formats are pinned in `contracts/` (vendored; schema_version **1**). The redaction floor is
governed by `contracts/redaction-vectors.json` AND `contracts/redaction-fixtures.json` — **lead with
those suites**; they are security-critical. Never change a wire format or a redaction behaviour here;
change it in the canonical contract in `e2e/contracts/` first, re-vendor to every implementation, and
keep all the suites green. Do not hand-roll regex detection: locate candidates, let the composed
validators decide (see `REDACTION.md`).

## Two traps this repo has already hit

- **`flanj/__init__.py` must stay lazy.** Python initializes a parent package before its submodule,
  so an eager `__init__` puts `asyncio` — and therefore sockets and TLS — behind `import
  flanj.redaction`, which makes the floor's zero-I/O property untestable. The module-graph audit
  fails if you un-lazy it.
- **Read result fields by wire name AND python name** (`flanj.mcp.result_meta.get_field`). The
  official `mcp` package exposes `structuredContent` as the attribute `structured_content`; the
  camelCase form is a serialization alias only. Reading the wire name alone captured an empty body
  from every real client while the entire unit suite stayed green — the stranger smoke caught it.
  `tests/mcp/test_real_models.py` is the regression.

## Conventions

One responsibility per module, snake_case filenames, type everything, avoid `Any` outside the
feature-detection boundary (where it is the honest type). Tests in `tests/`, Arrange-Act-Assert.
`git commit -s` — **DCO is enforced** (see CONTRIBUTING.md).

**A guard that has never failed is not known to work.** When adding a test that pins a defect, prove
it red against that defect first.

## Docs

`docs/CONCEPTS.md` (sanitized, public-safe engineering overview). Deeper local context lives in
`src/flanj/mcp/CLAUDE.md` (the MCP instrumentation, with its TypeScript twin per file) and `REDACTION.md`.
Community files mirror `flanj-io/sdk`'s: `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, the issue
and PR templates, `dependabot.yml`. **When one of them changes in `sdk`, change it here too.**
