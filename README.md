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

```python
from mcp import ClientSession
from flanj import instrument_mcp_client, otlp_logger

logger = otlp_logger(endpoint="http://localhost:4318/v1/logs", service_name="my-agent")

async with ClientSession(read_stream, write_stream) as session:
    instrument_mcp_client(session, integration="acme-tools", logger=logger)
    await session.initialize()
    # Use `session` exactly as before. Nothing about its behavior changes.
    result = await session.call_tool("get_balance", {"account_id": "acct_1"})
```

### Configuration

| Option / variable | Default | Meaning |
|---|---|---|
| `integration=` | *(required)* | Emitted as `flanj.integration`; one per MCP server you want to track separately. |
| `endpoint=` | detected from the transport | The streamable-HTTP URL. Its `host[:port]` is the edge key. |
| `server_kind=` | detected | `"streamable-http"` or `"stdio"`. A stdio server is the edge class `local-process`, keyed by its `serverInfo.name`. |
| `refetch_on_list_changed=` | `True` | On `notifications/tools/list_changed`, refetch the catalogue and re-snapshot. Same default as the TypeScript SDK. |
| `body_cap_bytes=` | `16384` | Per-body capture cap. |
| `FLANJ_OTLP_ENDPOINT` | — | Collector logs endpoint for `otlp_logger()`. Then `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`, then `OTEL_EXPORTER_OTLP_ENDPOINT` (+ `/v1/logs`). Default `http://localhost:4318/v1/logs`. |
| `FLANJ_SILENCE_CAPTURE_WARNINGS` | unset | Capture failures are fenced and never reach your app; the *first* one prints one line to stderr so a broken capture path is not silent. Set this to silence it. |

An application that already owns an OpenTelemetry `LoggerProvider` should pass its own logger instead of
calling `otlp_logger()`.

## What is captured

**Captured:** every `tools/call` and `tools/list` on an instrumented session, over any transport the
official client supports (streamable HTTP, stdio). For each call: the arguments as the request body,
`structuredContent` (else the `content[]` text) as the response body, the outcome (`isError`), the server's
identity from the result's `_meta`, and the JSON-RPC id your client generated, labeled as client-generated.
For each **complete** `tools/list`: the server's own declared schemas, verbatim, never re-inferred.

**Not captured:**

- **HTTP request/response bodies.** Python has no `node:http` choke point to patch the way the TypeScript SDK
  does. Per-library HTTP capture (`requests`/`httpx`/`aiohttp`) is not started.
- **`tasks/get` payloads.** A Tasks handle is recorded as an envelope with no body, so nothing models the
  envelope as the tool's output shape.
- **Sessions you did not instrument.** There is no auto-instrumentation path yet; call
  `instrument_mcp_client` on each session.

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
it end to end in our own e2e harness, with that lane's assertions green. Until then it says early,
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
