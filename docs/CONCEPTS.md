# Flanj — Concepts (engineering overview)

*This is a technical overview for contributors to the public `sdk`, `sdk-py` and `collector` repos. It
intentionally contains only the engineering model — not product strategy.*

## What Flanj does

Flanj is an integration-reliability tool. It captures the real traffic between a service or an agent and
a third-party API or MCP server it depends on, and validates that live traffic against the other side's
contract. For a REST provider the contract is its published OpenAPI spec. For an MCP server it is the
`tools/list` catalogue the server itself hands the client. When live traffic diverges from the contract
(a field changes type, a tool is renamed, a required input appears, an output stops matching its declared
schema), that **drift** is surfaced with the exact evidence: the redacted call that proves it.

## Two planes

- **Local plane (self-hosted, this is the OSS part):** capture, redaction, storage, drift detection, and a
  local UI — all inside the user's own environment. **Raw calls never leave.**
- **Control plane (hosted, separate/closed):** collaboration — when a user *references* a call to flag it,
  a redacted copy is promoted to a durable thread that the other side's engineer can open and reply to. The
  local plane only ever pushes outbound to the control plane; nothing peers inbound.

## The components in these public repos

- **`sdk`** — a thin OpenTelemetry (JS) distribution that adds HTTP request/response **body capture**, MCP
  client capture, and **redaction-at-source**.
- **`sdk-py`** (this repo) — the Python SDK: MCP client capture only, with the same redaction floor and the
  same OTLP record convention. It wraps the official `mcp` package's `ClientSession`; it never touches a
  transport.
- **`collector`** — an OpenTelemetry Collector distribution: receives the SDKs' OTLP, applies
  defense-in-depth redaction, runs drift detection near the source, stores redacted calls in a local store
  (a rolling window; embedded by default, or a customer-provided Postgres so several collector pods share
  one store), and serves a localhost UI. Headless and outbound-only apart from that UI.

For an MCP server the SDK forwards each complete `tools/list` as a **contract snapshot**, so the collector
has a baseline from the first call with nothing configured. Every later `tools/call` is checked against it.

## Non-negotiables (why the code is shaped the way it is)

1. **Redaction at source, before store or transmit.** A redaction floor — composed, hardened validators
   (Luhn-gated PAN, email, IBAN, phone) behind our own interface, with deep traversal of nested bodies and
   base64 decode-then-scan; local, zero external calls — is mandatory and runs before a body is ever
   attached to a record. It exists in Python, TypeScript and Go, and one shared fixture suite keeps all
   three byte-for-byte in parity. See `REDACTION.md`.
2. **Out of band.** Capture never changes a call, a result, or an error. A capture failure means "we
   stopped collecting", never "the application broke". In Python that includes not changing *when* things
   happen: no added suspension point, cancellation passed through untouched.
3. **Raw calls never leave the local environment.** Only a *referenced* (redacted) call is promoted to the
   control plane, and only when a human flags it.
4. **Outbound-only collector.** No inbound surface; the collector only pushes to the control plane.
5. **Technical adherence only.** Drift detection validates fields/types/shapes/enums — never business or
   economic correctness, which is legitimately variable.

## The contract

Cross-component wire formats (the OTLP attribute convention, the redacted-call record, the redaction
floor) are pinned in `contracts/` (vendored from a canonical source). The redaction floor is governed by
golden fixture files (scalar vectors + the cross-language parity battery) that every implementation
conforms to. Changes to any wire format go through the contract first. Behavioural defaults are shared
too: where the Python SDK must differ from the TypeScript one, the difference is documented in the
contract rather than chosen locally.
