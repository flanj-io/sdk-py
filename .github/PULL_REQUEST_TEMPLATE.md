<!-- Thanks for contributing to Flanj. Fill this out so review is quick. -->

## What and why

<!-- What does this change do, and why? Link any related issue: Closes #123 -->

## How was it tested?

<!-- Commands run, new or updated tests, manual verification. -->

## Checklist

- [ ] Commits are signed off for the DCO (`git commit -s`); see `CONTRIBUTING.md`.
- [ ] Tests pass locally (`pytest`), and lint and types are clean (`ruff check . && mypy`).
- [ ] If this touches capture or redaction, both redaction suites still pass and no raw
      body can reach an attribute, the store, or the wire before redaction.
- [ ] If this changes a cross-repo wire format, the change went through `contracts/` first.
- [ ] Docs and `CLAUDE.md` updated if behaviour or structure changed.
