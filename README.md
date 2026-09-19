<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/flanj-io/sdk/main/docs/brand/flanj-lockup-dark.svg">
  <img alt="Flanj" height="48" src="https://raw.githubusercontent.com/flanj-io/sdk/main/docs/brand/flanj-lockup.svg">
</picture>

# flanj — Flanj SDK for Python

**Your integration didn't break. It started being wrong.**
Every call succeeded. That's why nothing caught it.

**Early — MCP only.** See [Status](#status).

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![ci](https://github.com/flanj-io/sdk-py/actions/workflows/ci.yml/badge.svg)](https://github.com/flanj-io/sdk-py/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

`flanj` instruments an MCP client session (`mcp.ClientSession`). It records the `tools/list` catalogue
each MCP server hands your agent and the `tools/call` traffic that follows. It redacts sensitive data at the
source, then exports the redacted records over OTLP to a Flanj collector. The collector checks every call
against the contract the server published and flags drift.

**Trust posture.** Capture is out of band: the SDK wraps the session your agent already uses, and never
proxies, rewrites, delays or blocks a call. Arguments pass through by reference, the tool's own result
object is returned, and exceptions propagate unchanged. Redaction runs in your process, before a record is
exported. Redacted records go only to a collector you run in your own environment; bodies never leave
it. See [REDACTION.md](REDACTION.md) for the floor and how it is held identical across languages.

## Quick start

Needs **Python 3.10+** and a running Flanj collector, started with the collector README's
[Run it on a laptop](https://github.com/flanj-io/collector#run-it-on-a-laptop) block. Python 3.10 is the floor of the
official `mcp` package this SDK instruments, so there is no supported MCP client below it; an older runtime
is refused with one sentence rather than failing somewhere inside a capture path.

```bash
pip install flanj
```

> **Not yet on PyPI.** Until it is, install from source:
> `pip install git+https://github.com/flanj-io/sdk-py`

Make this the **first line** of your program — before anything imports `mcp`:

```python
import flanj.register  # noqa: F401
```

That is the whole integration. Every MCP client session your program opens afterwards is captured, redacted
and exported, and each server is placed on its own edge. It is the counterpart of the TypeScript SDK's
`node -r @flanj/sdk/register`, and prints one line on startup (`FLANJ_QUIET=1` silences it).

### Load flanj first

A Python `ClientSession` holds two in-memory streams and no URL, so the SDK learns where each MCP server is
when its transport *opens* — it wraps `streamable_http_client`, `sse_client` and `stdio_client`. A program that
did `from mcp.client.stdio import stdio_client` before flanj loaded holds the unwrapped function, and flanj
never sees those transports. The same rule applies to Datadog's `import ddtrace.auto`, for the same reason.

A session whose transport flanj never saw is not guessed at: its edge is **`unknown`**, its calls are recorded
**without bodies** (it might be an internal server, whose bodies are never read), and flanj says so once on
stderr, naming the fix.

### Instrumenting a session yourself

```python
import flanj                        # still first
handle = flanj.start()              # the OTLP pipeline; wraps the transport openers

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async with streamable_http_client("https://mcp.acme.com/mcp") as (read, write):
    async with ClientSession(read, write) as session:
        handle.instrument(session)  # or flanj.instrument_mcp_client(session, logger=handle.logger)
        await session.initialize()
        # Use `session` exactly as before. Nothing about its behavior changes.
        result = await session.call_tool("get_balance", {"account_id": "acct_1"})
```

To instrument every session without the zero-code entry, call
`flanj.register_mcp_auto_instrumentation(logger=handle.logger)` after `start()`.

### Configuration

| Option / variable | Default | Meaning |
|---|---|---|
| `FLANJ_INTEGRATION_ID` / `integration=` | one per server | Emitted as `flanj.integration`. Unset, each server gets its own id derived from its edge key (`mcp.acme.com` → `mcp-acme-com`), exactly as the collector derives one. |
| `OTEL_SERVICE_NAME` / `service_name=` | `flanj-consumer` | `service.name` on exported records. |
| `FLANJ_OTLP_ENDPOINT` / `otlp_endpoint=` | `http://localhost:4318/v1/logs` | The collector's logs endpoint. Then `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`, then `OTEL_EXPORTER_OTLP_ENDPOINT` (+ `/v1/logs`). If an export fails, the first failure prints one line. |
| `FLANJ_BODY_CAP_BYTES` / `body_cap_bytes=` | `16384` | Per-body capture cap. |
| `endpoint=` / `server_kind=` | detected | Only for a session whose transport flanj could not see: the streamable-HTTP URL (its `host[:port]` is the edge key), or `"stdio"`. |
| `refetch_on_list_changed=` | `True` | On `notifications/tools/list_changed`, refetch the catalogue and re-snapshot. Same default as the TypeScript SDK. |
| `FLANJ_QUIET` | unset | `1` silences the `flanj.register` startup line. |
| `FLANJ_SILENCE_CAPTURE_WARNINGS` | unset | Silences the one-time lines for a failed capture or an `unknown` edge. |

Records are flushed on normal exit and on SIGTERM / SIGINT (`flanj.flush_on_exit(handle)`, which
`flanj.register` installs), bounded to five seconds, after which your own signal handling runs as before.

**Edges.** A server reached over a URL is `external` or `internal` by its host, the same rule the collector
uses; internal servers are metadata-only. A server your app launched over stdio is `local-process`, keyed
by the name it reports, and its bodies are captured: it usually wraps someone else's API. Its snapshot also
records **how it was launched** (`npx @stripe/mcp@0.2.1 …`): the command and arguments only, each
floor-redacted, never the environment or working directory. A server flanj could not place is `unknown`,
metadata-only.

## What is captured

**Captured:** every `tools/call` and `tools/list` on an instrumented session, over any transport the
official client supports (streamable HTTP, stdio). For each call: the arguments as the request body,
`structuredContent` (else the `content[]` text) as the response body, the outcome (`isError`), the server's
identity from the result's `_meta`, and the JSON-RPC id your client generated, labeled as client-generated.
A call the server **rejected** (a JSON-RPC error rather than a result with `isError`) also records the
error's code.
For each **complete** `tools/list`: the server's own declared schemas, verbatim, never re-inferred.

**Not captured:**

- **HTTP request/response bodies.** Python has no `node:http` choke point to patch the way the TypeScript SDK
  does. Per-library HTTP capture (`requests`/`httpx`/`aiohttp`) is not started.
- **`tasks/get` payloads.** A Tasks handle is recorded as an envelope with no body, so nothing models the
  envelope as the tool's output shape.

Bodies are captured on external and `local-process` edges; an MCP server on an internal address is
metadata-only. Every captured body is redacted in your process before it is exported; see
[REDACTION.md](REDACTION.md) for what is redacted and how.

### MCP clients: the contract arrives with the traffic

REST drift detection needs a spec somebody published and kept accurate. MCP servers publish their contract
on every single call — `tools/list` **is** the spec. So the collector has the baseline from the first call
your agent makes, for every MCP server it touches, with nothing to configure.

That is not a convenience difference. "Nobody publishes an accurate OpenAPI spec" is the strongest practical
objection to drift detection on REST, and it does not apply to MCP at all. It matters most for agents, the most
drift-fragile API consumers anyone has built: an agent reads a tool's description to decide what to do, so a
description that changes under it changes what it does, and nothing anywhere logs an error. For this SDK
that is not one feature among several — it is the whole product.

### It stays out of the way

`call_tool` is a coroutine, so three properties matter more here than in a synchronous SDK. Each is
locked by a test rather than asserted in prose (`tests/mcp/test_async_transparency.py`):

- **cancellation passes through untouched**: a cancelled call is the caller withdrawing, not an outcome,
  so it is neither captured nor delayed;
- **no suspension point is added**: the wrapper awaits the wrapped coroutine and nothing else, so
  scheduling order is unchanged;
- **the result is read, never consumed**: capture holds no reference past the call and iterates nothing.

## Status

**Early — MCP only.** Not *Supported*: a language is called supported only once the whole loop runs on
it end to end in our own integration harness, with that suite's assertions green. Until then it says early,
here and everywhere else.

**Languages.** Node / TypeScript — **supported**: [`@flanj/sdk`](https://github.com/flanj-io/sdk), HTTP
egress and ingress plus the MCP client. Python — **early**: this package, MCP client only.

**Where this stops, said out loud.** No HTTP body capture (see *What is captured*). A call the collector
cannot check against a contract is captured and reported as **not validated**, never as conforming.
Pre-release (v0); see [docs/CONCEPTS.md](docs/CONCEPTS.md) for the engineering model and
[CLAUDE.md](CLAUDE.md) for the repo map.

Flanj turns a detection into something you can act on with the other team. The SDK is open source under
Apache-2.0; the [collector](https://github.com/flanj-io/collector) is source-available under the Elastic
License 2.0; the network layer that carries a flagged finding between the two teams is hosted.

## Development

```bash
uv venv --python 3.10 && uv pip install -e ".[dev]"
pytest                       # the floor's contract suites, the wire seam, the async contract
ruff check . && mypy         # lint and types
bash scripts/smoke-pack.sh   # build the wheel, install it into a FRESH venv, drive a real MCP server
```

## Security

Report vulnerabilities, including any redaction gap, privately — see [SECURITY.md](SECURITY.md). Never
include a real card number or real personal data.

## License

[Apache-2.0](LICENSE). Contributions require a DCO sign-off; see [CONTRIBUTING.md](CONTRIBUTING.md).
