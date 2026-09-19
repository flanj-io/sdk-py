# Redaction — the floor, how it is built, and how it stays identical across languages

This document is the engineering reference for the Flanj **redaction floor** as implemented in
this package: the mandatory card-number, personal-data and secret redaction applied to **every
captured body** — **at source, before anything is stored or transmitted**. It is the security
property everything else in Flanj rests on.

The floor exists in **three** languages and must behave identically:

| Where | Language | Role |
|---|---|---|
| SDK (Node) | TypeScript (`@flanj/redaction-patterns`) | redacts at the call site, before export |
| Control plane | TypeScript (same package) | DLP on human free-text |
| Collector | Go (`internal/redact`) | defense-in-depth re-scan of every ingested body |
| **SDK (Python)** | **this package (`flanj.redaction`)** | **redacts at the call site, before export** |

**The fixtures are the contract, not any implementation.** `contracts/redaction-vectors.json`
(18 cases) and `contracts/redaction-fixtures.json` (86 cases) are vendored byte-identically from
the canonical contract source, and every implementation runs the same two files.

---

## 1. Strategy: composed hardened validators behind our own swappable interface

No drop-in redaction engine qualifies for the floor in any of these languages (Luhn-validated PAN
across formats + deep structured recursion + base64 decode-then-scan + broad PII + zero external
calls). So the floor **borrows validators and owns the pipeline**:

- **We do not hand-roll regex for detection.** Our code only *locates* candidates structurally
  (digit-run chains, `+`-prefixed digit groups, `CC##…` tokens, email/IP shapes). Every *decision*
  to redact is made by a validator, and the validators live in `flanj/redaction/validators/`,
  deliberately apart from the locators.
- **We do not adopt a whole redaction engine.** Traversal, gating, decoding, anchoring and the
  token format are ours, so they are identical across languages and cannot be changed under us by
  a dependency.

### Validators composed, and where this package differs

| Pattern | TypeScript | Go | **Python (here)** |
|---|---|---|---|
| `PAN` | `validator.isLuhnNumber` | pure Luhn (`luhn.go`) | **owned** (`luhn.py`) |
| `EMAIL` | `validator.isEmail` | `govalidator.IsEmail` | **owned grammar port** (`validators/email.py`) |
| `IBAN` | `validator.isIBAN` | own mod-97 + registry (`iban.go`) | **owned** (`validators/iban.py`) |
| `PHONE` | `libphonenumber-js/max` | `nyaruka/phonenumbers` | `phonenumbers` |
| `SSN` | format-anchored | same | same |
| `CVV` | contextual (key-aware) | same | same |
| `TOKEN` | format-anchored; JWT header validated as a JSON object | same | same |
| `IP` *(optional)* | `validator.isIP` | `govalidator.IsIPv4/IsIPv6` | `ipaddress` (stdlib) |

**Why Luhn and IBAN are owned here.** `python-stdnum` supplies both and was the obvious
dependency. It is not used, because `stdnum/util.py` imports `ssl` at module scope, which puts
`socket`, `ssl` and `subprocess` into the module graph of a floor whose foundational property is
that it does no I/O. Both checks are fixed arithmetic — Luhn is twelve lines, IBAN is mod-97 plus
a length registry — and the Go collector already owns them for exactly this reason. The IBAN
registry here is copied from `collector/internal/redact/iban.go`, which derived it from the
TypeScript validator's country table, so all three accept the same countries.

**Why the email validator is a grammar port.** Every pure-Python email validator worth using
carries a DNS dependency. The TypeScript floor decides with `validator.isEmail` and the Go floor
with `govalidator.IsEmail` — **both of which are themselves grammar checks** — so this is the same
kind of decision function, not a new heuristic, and it is kept in `validators/` rather than in the
recognizer so the locate-then-decide split stays visible.

**Why the PAN gate is pure Luhn and not a credit-card check.** Brand/BIN-gated checks reject a
Luhn-valid 19-digit Visa, a Mir card, and any card whose BIN is missing from a table that drifts
independently per library. That would under-redact against the contract ("13–19 digit runs passing
Luhn") and make cross-language parity depend on BIN tables staying in sync forever. Luhn is a
fixed function; over-redaction of the rare Luhn-colliding identifier is the safe failure direction.

---

## 2. What the wrapper owns (and why)

1. **Deep traversal.** Dicts, lists — every scalar is scanned, keys included, undocumented nested
   fields included. Numbers/bools/`None` are untouched, **except** a 13–19 digit integer that
   passes Luhn (a PAN sent as a bare number) and a 3–4 digit number under a CVV key, which become
   string tokens. (`bool` is an `int` subclass in Python and is explicitly *not* a number here —
   the other two floors leave booleans alone and so must this one.)
2. **Luhn gating.** A 13–19 digit run is never redacted unless it passes Luhn. The non-Luhn 16-digit
   `order_id` survives; a 4-digit `last4` and an integer `amount` are never touched.
3. **Base64 decode-then-scan.** Any run of ≥ 20 base64 chars that decodes to printable UTF-8 text is
   scanned; on a hit the **whole encoded run** becomes the token of the highest-precedence pattern
   found. Binary blobs, hashes and ordinary long words decode to non-text and are never scanned.
   Depth 1.
4. **Normalization.** Separators (`4-4-4-4`, `4-6-5` Amex, `4-4-4-4-3`, dashes) are stripped for
   detection; the **original span** is redacted. Every sub-chain of ≤ 5 groups is searched,
   longest first, because a leftmost-greedy regex tests the wrong window and leaks.
5. **Token format.** `⟦REDACTED:<TYPE>⟧` (U+27E6/U+27E7). Tokens are inert to re-scan, which gives
   idempotency and lets the collector re-apply the floor safely.
6. **Anchoring.** Candidates are anchored against `[A-Za-z0-9_]` on both sides: a Luhn-valid run
   glued inside an identifier (`TXN4111111111111111`, a UUID, a hex digest) is not a candidate.
   Phone requires a `+` country code. **Application order** is TOKEN, CVV, IBAN, PHONE, PAN, EMAIL,
   SSN, (IP): PHONE precedes PAN because the `+`-anchored phone locator can never eat a PAN, but
   the PAN chain scan can eat a phone's national part plus trailing digits when they pass Luhn.
7. **Fail-closed, zero I/O.** See §3.

### The text path

Bodies arrive as strings. Rather than parse → clone → re-serialize (which reorders keys and
reformats numbers differently in each language), the text path **scans the text and rewrites only
the scalars that fired, in place** — JSON through a tolerant scanner (keys too; values with their
key as context; truncated and malformed bodies scanned as plain-text residue, so **every byte is
scanned by some path**), form-urlencoded per percent-decoded pair, anything else as one scalar.
Because only fired scalars are rewritten, all three implementations emit **the same bytes**.

---

## 3. Zero I/O, enforced three ways

The floor is a pure function of its input. In this package that is not a convention, it is three
tests:

| Check | File | What it proves |
|---|---|---|
| Runtime sentinel | `tests/redaction/test_no_network.py` | arms every socket / DNS / subprocess primitive, runs the **entire** battery through both entry points plus the enhancer, and fails if anything was touched. Includes a self-test that the sentinel can fire. |
| Static import ban | `tests/redaction/test_import_hygiene.py` | walks the AST of every module under `flanj/redaction/` and fails on a network, filesystem or subprocess import. The analogue of the TypeScript ESLint `no-restricted-imports` ban. |
| Module-graph audit | `tests/redaction/test_module_graph.py` | in a **fresh interpreter**, imports and exercises the floor and asserts no network-capable module reached `sys.modules` — our dependencies' imports, not just ours. The analogue of the Go `go list -deps` audit. |

The third is why `flanj/__init__.py` exports lazily (PEP 562): Python initializes a parent package
before its submodule, so an eager `__init__` would put `asyncio` — and therefore sockets and TLS —
behind `import flanj.redaction` and make the property untestable.

---

## 4. Cross-language parity: enforced, not assumed

| File | What it pins |
|---|---|
| `redaction-vectors.json` | scalar/recognizer-level golden vectors (text in → text out + fired patterns) |
| `redaction-fixtures.json` | the structured battery: many PAN formats, PANs in arrays / nested / undocumented fields / keys / as numbers, base64 (std, url-safe, whole-body, embedded), inbound bodies, truncated and malformed bodies, the negatives that must survive, idempotency, and the poisoned-spec enhancer cases |

For every `json` case both entry points are asserted — structural `redact(value)` and the text path
over the serialized body, parsed back — by **deep equality**, the parity oracle. `text` cases must
match **byte-for-byte**. Every case must be idempotent.

**One gap deep equality cannot see, and what closes it.** Mapping equality is order-insensitive in
Python (and in JavaScript), but `flanj.redaction.fields` reaches the collector as *one serialized
string*, where key order is bytes. Moving `integer` out of last place left all 506 assertions of
the battery green. `tests/redaction/test_field_wire_order.py` pins the serialized form and was
proved red against exactly that defect.

**Known divergence class** (pinned down by the fixtures, not eliminated): the email and IBAN
validators are different implementations per language, so exotic inputs (quoted local parts, a
BBAN with a letter where a country's format says digits) may be judged differently. The fixtures
pin the real-world shapes; **add a fixture before relying on any new shape.**

**Adding a case:** edit the canonical contract source, re-vendor byte-identically to
every implementation, make all the suites green.

---

## 5. The schema-aware enhancer — ADD-only, never subtract

Above the floor sits a spec-driven `enhance(value, spec)`, applied to the floor's **output** with a
list of `{path, type}` fields a provider spec marks sensitive. It may only **add** tokens: it only
replaces a scalar carrying **no** token; a scalar the floor already touched is **immutable** to it,
so a poisoned spec cannot relabel a PAN as EMAIL and there is no operation by which it could
un-redact anything. The **never-subtract law** is asserted over the cross product of every `json`
fixture × every spec in the file, plus a hostile spec that points at every floor-redacted field
with the wrong type.

## 6. Invariants (all enforced by tests)

1. **Add-only** — redaction only replaces sensitive spans; it never un-redacts; the enhancer can only add.
2. **Idempotent** — `redact(redact(x)) == redact(x)`; a token is a fixed point.
3. **Redact before store/emit** — the SDK keeps only the redacted string; no raw body is ever set as an attribute, stored or transmitted, even transiently.
4. **Zero external calls** — sentinel + static ban + module-graph audit.
5. **Parity** — the same body redacts identically in all three languages (shared fixtures, deep-equal / byte-exact).

## 7. Reporting a redaction gap

A body that reaches storage or the wire with a raw card number or personal data is a security
issue. Report it privately per [SECURITY.md](./SECURITY.md) — include the synthetic payload shape;
never a real card number.
