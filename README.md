# flanj — Flanj SDK for Python

**Early — MCP only.**

Out-of-band capture of MCP client traffic, **redacted at source**, exported as OTLP log
records to a collector you run. Raw request and response bodies never leave your process:
the redaction floor runs before anything is attached or emitted.

```
your agent → (flanj captures + redacts) → OTLP/HTTP :4318 → collector you run
```

Apache-2.0. The collector is a separate self-hosted component; this SDK talks to it and to
nothing else.

## What this is for

The API changed and nothing threw an error. A tool's `outputSchema` said `amount` was an
integer; today it is a string. The call returned `200 OK`, your agent parsed it, and the
wrong number went downstream. Nothing in your stack is wired to notice that, because
nothing failed.

This SDK is the capture half: it records what an MCP server actually returned, against what
that server said it would return, so the difference is visible.

## Requirements

**Python 3.10+**. That is the floor of the official `mcp` package this SDK instruments, so
there is no supported MCP client below it. `start`-time code refuses to run on an older
runtime with one sentence rather than failing somewhere inside a capture path.

## Install

```bash
pip install flanj
```

> Not yet published to PyPI. Until it is, install from source:
> `pip install git+https://github.com/flanj-io/sdk-py`

## Quick start

```python
from mcp import ClientSession
from flanj import instrument_mcp_client, otlp_logger

logger = otlp_logger(endpoint="http://localhost:4318/v1/logs", service_name="my-agent")

session = ClientSession(read_stream, write_stream)
instrument_mcp_client(session, integration="acme-tools", logger=logger)

# Use `session` exactly as before. Nothing about its behaviour changes.
result = await session.call_tool("get_balance", {"account_id": "acct_1"})
```

Set `FLANJ_OTLP_ENDPOINT` instead of passing `endpoint=` if you would rather configure it
from the environment; `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` and `OTEL_EXPORTER_OTLP_ENDPOINT`
are honoured too, in that order.

## What gets captured

| | |
|---|---|
| `tools/call` | one record per call: arguments as the request body, `structuredContent` (else `content[]` text) as the response body, both floor-redacted |
| `tools/list` | one `contract_snapshot` per **complete** list — the server's own declared schemas, verbatim, never re-inferred |

**Not captured:** HTTP request/response bodies. Python has no `node:http` choke point to
patch the way the TypeScript SDK does, and an agent application has MCP traffic to watch
rather than a REST integration. MCP-only is a complete product for that shape, not a partial
SDK. Also not captured: `tasks/get` payloads (a Tasks handle is recorded as an envelope,
with no body, so nothing models the envelope as the tool's output shape).

## It stays out of the way

`instrument_mcp_client` is strictly out-of-band. Arguments pass through by reference,
the tool's own result object is returned, exceptions propagate untouched, and a capture
failure means *we stopped collecting* — never *the agent broke*.

Because `call_tool` is a coroutine, three properties matter more here than in a synchronous
SDK, and each is locked by a test rather than asserted in prose
(`tests/mcp/test_async_transparency.py`):

- **cancellation passes through untouched** — a cancelled call is the caller withdrawing,
  not an outcome, so it is neither captured nor delayed;
- **no suspension point is added** — the wrapper awaits the wrapped coroutine and nothing
  else, so scheduling order is unchanged;
- **the result is read, never consumed** — capture holds no reference past the call and
  iterates nothing.

## Redaction

Card numbers, personal data and secrets are removed **at the call site, before export**.
The floor is shared, by contract, with the Go collector and the TypeScript SDK: two fixture
files — not any implementation — are the specification, and all three suites run them.

It does no I/O. That is enforced three ways: a runtime sentinel that arms every socket, DNS
and subprocess primitive and runs the whole battery through it; a static ban on I/O-capable
imports in the floor's own source; and an audit of the whole import graph, which is why the
floor owns its Luhn and IBAN checks rather than taking a dependency that imports `ssl`.

See [REDACTION.md](REDACTION.md).

## Development

```bash
uv venv --python 3.10 && uv pip install -e ".[dev]"
pytest                    # the floor's contract suites, the wire seam, the async contract
ruff check . && mypy      # lint and types
bash scripts/smoke-pack.sh   # build the wheel, install it into a FRESH venv, run it
```

`scripts/smoke-pack.sh` is the one that matters before a release: green in the repo is not
the same as working for a stranger.

## Status

**Early — MCP only.** Not `Supported`: that word is reserved for a language whose end-to-end
lane is green in the integration harness, per the promotion rule this project keeps.

## Security

Report a redaction gap privately — see [SECURITY.md](SECURITY.md). Include the synthetic
payload shape; never a real card number.
