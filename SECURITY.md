# Security policy

## Reporting a vulnerability

Report privately to **security@flanj.io**. Please do not open a public issue for a
security report.

We aim to acknowledge within two business days.

## Reporting a redaction gap

A body that reaches storage or the wire carrying a raw card number or personal data is a
security issue, and it is the one we most want to hear about — the redaction floor is the
property everything else in Flanj rests on.

Include **the synthetic payload shape**, never a real card number, real personal data, or a
real credential. A minimal reproducing input and the expected-versus-actual redacted output
is ideal.

## Scope

In scope: the redaction floor (`flanj.redaction`), anything that could place an unredacted
value on the wire, and the MCP instrumentation's handling of untrusted server responses.

Out of scope: the behaviour of the `mcp` package itself, and of any MCP server you connect
to. Report those upstream.
