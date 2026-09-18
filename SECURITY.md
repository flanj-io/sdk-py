# Security policy

## Reporting a vulnerability

Flanj reads real API traffic, and MCP tool calls routinely carry sensitive and regulated data. The
whole reason this SDK exists is to keep that data from leaking. Capture is out of band and
redaction runs at the source, in your process; a gap in either is a security issue.

**Do not report security vulnerabilities through public GitHub issues.**

Report them privately through one of:

- GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  ("Report a vulnerability" under the **Security** tab), or
- email **security@flanj.io**.

Include:

- a description of the issue and its impact,
- steps to reproduce (a minimal proof of concept if possible),
- affected version(s) / commit,
- any suggested mitigation.

We will acknowledge your report within 3 business days and aim to give a
remediation timeline within 10 business days. We ask for a reasonable window to
release a fix before any public disclosure, and we will credit you in the
advisory unless you prefer to remain anonymous.

## Redaction

The SDK captures MCP tool arguments and results, so redaction is the security property everything
else rests on. How it is designed is documented in [REDACTION.md](./REDACTION.md); the guarantees are:

- **Redaction at source.** Every captured body is run through the redaction floor (`flanj.redaction`)
  in your process before a record is built, and only the redacted string is kept. No raw body is ever
  set as an attribute, stored, or transmitted, not even transiently. Internal edges are metadata-only.
  Redacted records go only to a collector you run in your own environment.
- **Local, zero external calls.** The floor is a pure function of its input. It never performs
  network, DNS, process or filesystem I/O. This is enforced three ways: a static ban on every such
  import in the floor's source, a runtime network sentinel that runs the entire redaction battery,
  and an audit of the floor's whole import graph in a fresh interpreter. Its one third-party
  validator, `phonenumbers`, is offline with no network code paths. The Luhn and IBAN checks are
  owned rather than borrowed, because the obvious library for them imports `ssl` at module scope.
- **Hardened, not hand-rolled.** Detection decisions are made by validators (Luhn for card numbers,
  mod-97 for IBANs, phone metadata for numbers, a strict email grammar); the floor's own code only
  locates candidates, recurses nested structures, decodes base64, and anchors matches.
- **Cross-language parity.** The same floor exists in TypeScript and in the collector's Go, which
  re-applies it as defense in depth. A shared fixture suite (`contracts/redaction-fixtures.json`) is
  run by all three test suites, so the same payload redacts identically in each.
- **Add-only, idempotent.** Tokens (`⟦REDACTED:<TYPE>⟧`) are never un-redacted and never
  double-wrapped; schema-aware redaction can only add above the floor, never subtract.

### Reporting a redaction gap

**Any path by which a raw card number or personal data can reach storage or the wire unredacted
is a security issue and is in scope.** That includes a payload shape the floor does not recognise, an
encoding it does not decode, or a difference between the Python, TypeScript and Go behaviour. Report
it privately as above. A minimal, **synthetic** payload that reproduces the gap is the most useful
thing you can include (use public test card numbers; never a real card number or real personal data).

## Scope

Also in scope: the MCP instrumentation's handling of untrusted server responses. A hostile or
malformed server must degrade capture, never break or alter the application.

Out of scope: the behaviour of the official `mcp` package itself, and of any MCP server you connect
to. Report those upstream.
