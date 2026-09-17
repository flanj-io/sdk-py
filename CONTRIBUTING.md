# Contributing

Thanks for helping. This repository is public and Apache-2.0.

## Developer Certificate of Origin (DCO)

Every commit must be signed off:

```bash
git commit -s -m "your message"
```

That adds a `Signed-off-by:` line certifying you wrote the patch or have the right to submit
it under the project's licence — see [developercertificate.org](https://developercertificate.org/).
CI enforces it on every non-merge commit.

## Before you open a PR

```bash
uv venv --python 3.10 && uv pip install -e ".[dev]"
pytest
ruff check . && mypy
```

## Two things to know before changing anything

**`contracts/` is vendored — do not hand-edit it.** Those files are byte-identical copies of
a contract shared with the Flanj collector and the TypeScript SDK. Changing redaction
behaviour or the wire format means changing the canonical contract first and re-vendoring to
every implementation, so all the suites stay green together. A local edit here makes this
SDK disagree with the collector, silently.

**Never hand-roll regex detection in the redaction floor.** Our code only *locates*
candidates structurally; every decision to redact is made by a validator. This is the rule
that keeps three languages in agreement, and it is why the floor over-redacts a rare
Luhn-colliding identifier rather than under-redacting a card. See [REDACTION.md](REDACTION.md).

## Tests

A fix without a regression test is not finished. If you are adding a test that guards a
defect, **prove it red first** against the defect, then green with the fix — a guard that has
never failed is not known to work.
