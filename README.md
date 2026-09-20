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
[Run it on a laptop](https://github.com/flanj-io/collector#run-it-on-a-laptop) block. Use that command as
written: the collector's UI binds container loopback by design, so it is reached through the small sidecar
that block includes, and a plain `docker run -p 5335:5335` publishes nothing.
Python 3.10 is the floor of the official `mcp` package this SDK instruments, so there is no supported MCP
client below it; an older runtime is refused with one sentence rather than failing somewhere inside a
capture path.

```bash
pip install flanj
```

> **Not yet on PyPI.** Until it is, install from source:
> `pip install git+https://github.com/flanj-io/sdk-py`

Make this the **first line** of your program — before anything imports `mcp`:

```python
import flanj.register  # noqa: F401
```

That is the whole integration; no other source change. It starts the OTLP pipeline, flushes on exit and
auto-instruments every MCP client session your program opens afterwards, placing each server on its own
edge. It prints one line naming the endpoint and the resolved service name (`FLANJ_QUIET=1` silences it).
It is the counterpart of the TypeScript SDK's `node -r @flanj/sdk/register`.

**Verify** — after your agent has made at least one tool call, and assuming the collector was started with
the [Run it on a laptop](https://github.com/flanj-io/collector#run-it-on-a-laptop) command including its UI
sidecar:

```bash
curl -s http://127.0.0.1:5335/api/health
```

then open <http://127.0.0.1:5335> and look at the **Traffic** tab: your tool call should be there, redacted.

If that `curl` answers `Failed to connect`, the SDK is not what failed: the collector's UI is loopback-only
inside its container and nothing is forwarding to it. Re-run the collector with that block's sidecar. Ingest
on `:4318` is a separate, ordinary published port and works either way.

### Load flanj first

A Python `ClientSession` holds two in-memory streams and no URL, so the SDK learns where each MCP server is
when its transport *opens* — it wraps `streamable_http_client`, `sse_client` and `stdio_client`. A program that
did `from mcp.client.stdio import stdio_client` before flanj loaded holds the unwrapped function, and flanj
never sees those transports. The same rule applies to Datadog's `import ddtrace.auto`, for the same reason.

A session whose transport flanj never saw is not guessed at: its edge is **`unknown`**, its calls are recorded
**without bodies** (it might be an internal server, whose bodies are never read), and flanj says so once on
stderr, naming the fix. `unknown` is the one behaviour this SDK has that the TypeScript SDK does not; a
JavaScript MCP client keeps its transport, so it can always place a server.

### MCP quick start

Nothing is configured per server. With the zero-code entry loaded, an ordinary session is already captured:

```python
import flanj.register  # noqa: F401  — first line, before `mcp` is imported

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async with streamable_http_client("https://mcp.acme.com/mcp") as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        await session.list_tools()                                  # -> a contract snapshot
        await session.call_tool("get_balance", {"account_id": "x"}) # -> a captured, redacted call
```

**For each `tools/call`:** the arguments as the request body; `structuredContent` — else the `content[]`
text — as the response body; the outcome (`isError`); the server's identity from the result's `_meta`; and
the JSON-RPC request id your client generated, labelled as client-generated. A call the server **rejected**
(a JSON-RPC error rather than a result with `isError`) also records the error's code. A Tasks handle
(`tasks/get`) is recorded as an envelope with **no body**, so nothing models the envelope as the tool's own
output shape.

**For each complete `tools/list`:** the server's own declared schemas, verbatim, never re-inferred. The
catalogue is refetched and re-snapshotted on `notifications/tools/list_changed`
(`refetch_on_list_changed`, on by default), so a server that changes its tools mid-session is caught when it
does.

**For a server your app launched over stdio:** how it was launched (`npx @stripe/mcp@0.2.1 …`) — the command
and its arguments only, each floor-redacted, never the environment or the working directory.

**Your service's name** is the only thing you configure, and it defaults to your app's own name
(`python -m myapp` → `myapp`), then `flanj-sdk`. It travels as the OTLP resource `service.name`, and the
collector shows it as a **Service** column beside the counterparty and as a Traffic filter. It names your
own internal topology, so it stays on your collector: a service name is **never sent to the control plane**.

### Instrumenting a client yourself

```python
import flanj                        # still first
handle = flanj.start()              # the OTLP pipeline; wraps the transport openers

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async with streamable_http_client("https://mcp.acme.com/mcp") as (read, write):
    async with ClientSession(read, write) as session:
        handle.instrument(session)  # this handle's logger and body cap
        await session.initialize()
        # Use `session` exactly as before. Nothing about its behavior changes.
        result = await session.call_tool("get_balance", {"account_id": "acct_1"})
```

To instrument every session without the zero-code entry, call
`flanj.register_mcp_auto_instrumentation(logger=handle.logger)` after `start()`.

### Configuration

| Option / variable | Default | Meaning |
|---|---|---|
| `OTEL_SERVICE_NAME` / `service_name=` | the app's own name, else `flanj-sdk` | `service.name` on exported records. Precedence: explicit `service_name=`, then `OTEL_SERVICE_NAME`, then the running script or module's own name (`python -m myapp` → `myapp`; `python path/app.py` → `app`), then `flanj-sdk`. The collector derives each record's integration itself; this SDK never sends `flanj.integration`. |
| `FLANJ_OTLP_ENDPOINT` / `otlp_endpoint=` | `http://localhost:4318/v1/logs` | The collector's logs endpoint. Then `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`, then `OTEL_EXPORTER_OTLP_ENDPOINT` (+ `/v1/logs`). If an export fails, the first failure prints one line. |
| `FLANJ_BODY_CAP_BYTES` / `body_cap_bytes=` | `16384` | Per-body capture cap. |
| `endpoint=` / `server_kind=` | detected | Only for a session whose transport flanj could not see: the streamable-HTTP URL (its `host[:port]` is the edge key), or `"stdio"`. |
| `refetch_on_list_changed=` | `True` | On `notifications/tools/list_changed`, refetch the catalogue and re-snapshot. Same default as the TypeScript SDK. |
| `FLANJ_QUIET` | unset | `1` silences the `flanj.register` startup line. |
| `FLANJ_SILENCE_CAPTURE_WARNINGS` | unset | Silences the one-time lines for a failed capture or an `unknown` edge. Same variable, same lines, in the TypeScript SDK. |

Records are flushed on normal exit and on SIGTERM / SIGINT (`flanj.flush_on_exit(handle)`, which
`flanj.register` installs), bounded to five seconds, after which your own signal handling runs as before.

## What is captured

**Captured:** every `tools/call` and `tools/list` on an instrumented session, over any transport the
official client supports (streamable HTTP, stdio). The fields are listed under
[MCP quick start](#mcp-quick-start).

**Not captured:**

- **HTTP request/response bodies.** Python has no `node:http` choke point to patch the way the TypeScript SDK
  does. Per-library HTTP capture (`requests`/`httpx`/`aiohttp`) is not started. This is the one intended
  difference between the two SDKs.
- **`tasks/get` payloads.** A Tasks handle is recorded as an envelope with no body, so nothing models the
  envelope as the tool's output shape.

**Edges.** A server reached over a URL is `external` or `internal` by its host, the same rule the collector
uses; internal servers are metadata-only. A server your app launched over stdio is `local-process`, keyed
by the name it reports, and its bodies are captured: it usually wraps someone else's API. A server flanj
could not place is `unknown`, metadata-only. Every captured body is redacted in your process before it is
exported; see [REDACTION.md](REDACTION.md) for what is redacted and how.

**When capture itself fails** it stops collecting and says so — once, on stderr, naming what broke and that
your application is unaffected. Silence is the failure mode this SDK exists to remove, and a collector
showing nothing looks exactly like an agent making no calls. `FLANJ_SILENCE_CAPTURE_WARNINGS=1` turns the
line off once you have read it.

### MCP clients: the contract arrives with the traffic

REST drift detection needs a spec somebody published and kept accurate. MCP servers publish their contract
on every single call — `tools/list` **is** the spec. So the collector has the baseline from the first call
your agent makes, for every MCP server it touches, with nothing to configure and nothing to upload: the
observed `tools/list` is forwarded as a contract snapshot, versioned by content hash, and every later
`tools/call` is checked against it.

That is not a convenience difference. "Nobody publishes an accurate OpenAPI spec" is the strongest practical
objection to drift detection on REST, and it does not apply to MCP at all. It matters most for agents, the most
drift-fragile API consumers anyone has built: an agent reads a tool's description to decide what to do, so a
description that changes under it changes what it does, and nothing anywhere logs an error. For this SDK
that is not one feature among several — it is the whole product.

There is nothing to configure per server: the collector derives each MCP server's integration from its peer
host (or, over stdio, the name it reports), so two servers never share a baseline.

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
egress and ingress plus the MCP client. Python — **early**: this package, MCP client only. Apart from HTTP
capture the two are the same SDK: same defaults, same records, same entry points.

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
