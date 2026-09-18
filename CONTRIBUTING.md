# Contributing to the Flanj SDK for Python

Thanks for your interest in contributing. This repository is licensed under Apache-2.0.

## Developer Certificate of Origin (DCO)

All contributions to this repository must be signed off under the
[Developer Certificate of Origin](https://developercertificate.org/). This certifies that you wrote or
otherwise have the right to submit the code you are contributing.

Sign off every commit by adding a `Signed-off-by` trailer with your real name and email:

```
Signed-off-by: Jane Doe <jane@example.com>
```

The easiest way is `git commit -s`. PRs with unsigned commits will not be merged; CI enforces the DCO check.

## Ground rules

- Keep this package Apache-2.0 throughout; legal and compliance teams at regulated organizations inspect
  it. Do not add code under copyleft or source-available licenses, and do not depend on packages that are
  not Apache, MIT, BSD, ISC or PSF.
- **Redaction is the security bar.** Capture is out of band and redaction runs at the source, in the
  user's process. Any change touching capture or redaction must keep both redaction suites green
  (`contracts/redaction-vectors.json` and `contracts/redaction-fixtures.json`) and must never let a raw
  body reach an attribute, the store, or the wire before redaction.
- **Never hand-roll regex detection in the floor.** Our code only *locates* candidates; every decision
  to redact is made by a validator. That rule is what keeps three languages in agreement. See
  [REDACTION.md](REDACTION.md).
- **The floor does no I/O** — and "no I/O" includes the import graph. Check what a new dependency
  imports at module scope, not just what it calls.
- Follow the contract in `contracts/` (vendored from the canonical source; do not hand-edit it).
  Wire-format and redaction changes go through the contract first, not here.
- **Defaults match the TypeScript SDK.** A genuinely Python-specific difference is documented in the
  contract, never introduced as a one-line default.

## Workflow

1. Branch, write tests first (lead with redaction), implement. A test that guards a defect is proved
   red against that defect before it is kept.
2. Run the gate:

   ```bash
   uv venv --python 3.10 && uv pip install -e ".[dev]"
   pytest
   ruff check . && mypy
   bash scripts/smoke-pack.sh
   ```

3. `git commit -s`, open a PR. CI runs the tests on the floor and the latest Python, lint, types, the
   stranger smoke on the built wheel, and the DCO check.
