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

## Releasing

Publishing to PyPI is entirely `.github/workflows/release.yml`, triggered by a `v*` tag. It builds the
wheel and sdist, verifies them (tag/version match, `twine check --strict`, wheel contents, and — the
check that matters — installing the built wheel into a clean virtualenv on both the floor Python and
the newest one CI tests, then checking the zero-code entry's startup notice), uploads to PyPI via
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OpenID Connect — no API token exists
for this to leak), then verifies the upload by installing it back anonymously from PyPI.

1. **Bump the version.** Open a PR that sets `__version__` in `src/flanj/version.py` to the number
   you're releasing (PEP 440), merge it.
2. **Tag a freshly fetched `main`** — not a stale local checkout, and never a feature branch. GitHub
   reads a tag's workflows from that tag's own tree, so tagging anything else either runs stale checks
   or, if `release.yml` did not exist yet at that commit, runs nothing at all, silently:

   ```bash
   git fetch origin
   git tag -a vX.Y.Z origin/main -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

   Then confirm a run actually started — `gh run list --workflow=release.yml -R flanj-io/sdk-py` — rather
   than assuming the push triggered it.
3. **Watch it.** The tag push itself runs the real thing (no `dry_run` flag to check): build, verify,
   upload, verify again from PyPI.

### Proving the workflow without publishing

`workflow_dispatch` on `release.yml` takes a `tag` and a `dry_run` input (default `true`). A dry run
executes every step above except the actual upload — same build, same tag/version check, same
`twine check --strict`, same install-and-startup-notice check on both Pythons — so a change to the
workflow, or a release candidate, can be proven before it can cost a real publish:

```bash
gh workflow run release.yml -R flanj-io/sdk-py --ref <branch> -f tag=v0.2.0 -f dry_run=true
```

Note: `workflow_dispatch` only works once the workflow file exists on `main` (or, for a run on another
ref, once GitHub already knows about the workflow from `main`). Before that, run the same checks by hand:
`uv build`, `twine check --strict`, `python scripts/check-wheel-contents.py`, and
`scripts/verify-install.sh <python-version> <version> <wheel-path>` — see `.github/workflows/release.yml`
for the exact invocations.

### One-time setup (repository owner only)

Trusted Publishing has to be registered on PyPI before the first tag can be pushed; nobody else can do
this. On [pypi.org](https://pypi.org), under this project's **Publishing** settings, add a new GitHub
publisher with:

| Field | Value |
|---|---|
| Owner | `flanj-io` |
| Repository name | `sdk-py` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

No secret is created or stored anywhere — PyPI exchanges the workflow run's OIDC token for a short-lived
upload credential scoped to that one run.

### After the first real publish

Once `flanj` is genuinely installable (`pip install flanj` succeeds and imports), open a follow-up PR
that removes the README's "Not yet on PyPI" note and its `pip install git+https://...` fallback — not
before, or the README would claim something not yet true.
