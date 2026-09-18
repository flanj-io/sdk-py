# CLAUDE.md — `src/flanj/mcp/`

The Python twin of the TypeScript SDK's `src/mcp/`: instrument the MCP **client session** and turn an
agent's `tools/list` / `tools/call` into the same capture → detect loop a REST integration rides.
Transport-independent by design — we wrap the `ClientSession` object, never a transport (no proxying, no
stdio process spawning, no HTTP sniffing) — and the wrapper is strictly **out-of-band**: it never changes
a call, a result, an error, or the *timing* of any of them. Capture failure = "we stopped collecting",
never "the agent broke".

## Files (one concern each)

| File | Role | TypeScript twin |
|---|---|---|
| `instrument.py` | `instrument_mcp_client(session, ...)` — binds `list_tools`/`call_tool` wrappers on the instance. `list_tools` pages accumulate across the caller's cursor chain and emit **one `contract_snapshot` per complete list**, keyed to the chain's expected next cursor. `notifications/tools/list_changed` (via the CHAINED `_message_handler`; the app's own handler still runs) triggers a bounded refetch on the **session's own task group**, default on, as in TS. The JSON-RPC id is observed on the dispatcher's outgoing `_write` (private API: feature-detected, degrades to omitting the optional attribute) and attributed per **task** via a `ContextVar` — client-generated, labeled as such. | `instrument-mcp-client.ts` |
| `assemble_call.py` | `assemble_mcp_call` — funnels through the ONE shared `assemble_captured_call`, so every floor rule applies identically. Slots: method `"tools/call"`, route/target `"/<tool>"`, url `"mcp://<peer>/<tool>"`, status 0. Request body = arguments; response body = `structuredContent` else joined `content[]` text. | `assemble-mcp-call.ts` |
| `assemble_snapshot.py` | Projects each tool onto the ToolDef wire keys, adds server identity, then floor-redacts the whole JSON before anything is attached. Schemas verbatim; an absent `outputSchema` stays absent. | `assemble-contract-snapshot.ts` |
| `resolve_edge.py` | Edge identity: streamable-HTTP → endpoint `host[:port]` through the shared external/internal heuristic; stdio → `serverInfo.name`, class **`local-process`**. | `resolve-mcp-edge.ts` |
| `record.py` | Call and snapshot records → the CONTRACTS §2 rows (HTTP attribute set plus `flanj.transport`/`flanj.mcp.*`, minus `flanj.http.status_code`). Emits through either shape of the OTel logs API, detected from the signature. | `mcp-record.ts` |
| `result_meta.py` | The **protocol revision 2026-07-28** readers, all total and read-only: server identity, W3C trace context, `resultType`, Tasks handles, catalogue cache hints. Also `get_field`, which reads every protocol field by wire name **and** python name. | `result-meta.ts` |
| `types.py` | The shared shapes. | `mcp-types.ts` |

**No twin for `auto-instrument.ts`.** There is no auto-instrumentation path in Python yet: the caller
instruments each session.

## Never break

- **Pass-through is the contract.** The result object itself is returned, arguments are passed by
  reference, errors re-raised unchanged, a throwing capture sink swallowed.
  `tests/mcp/test_async_transparency.py`.
- **The async contract.** `except Exception` — never `except BaseException`; cancellation is re-raised
  untouched and never captured; no `await` beyond the wrapped one; the result is read, never iterated.
  Each of these tests was proved red against its defect. This is the bug class that shipped once already
  in the other runtime.
- **Read fields by wire name AND python name** (`get_field`). The `mcp` package exposes
  `structuredContent` only as `structured_content`; a wire-name read captured an empty body from every
  real client while every dict-based test stayed green. `tests/mcp/test_real_models.py`.
- **Golden lock:** `tests/mcp/test_golden_otlp.py` asserts the FULL attribute map against
  `contracts/golden-otlp-mcp-call.json` / `-snapshot.json`, in both directions.
- **One snapshot per COMPLETE list.** A failed page ends the chain and emits nothing partial.
- **Identity comes from `_meta`, not the handshake**, and is sticky; the handshake accessors are only
  the fallback. A stdio edge is keyed by `serverInfo.name`, so without it every local server collapses
  onto `unknown-mcp-server`.
- **An `input_required` result and a Tasks handle are not evidence.** Both are captured and marked; a task
  handle's body is dropped.
- **Defaults match the TypeScript SDK** (`refetch_on_list_changed=True` is pinned by a test).

## Wiring

`instrument_mcp_client(session, integration=..., endpoint=None, server_kind=None, logger=None,
on_capture=None, on_snapshot=None, refetch_on_list_changed=True, body_cap_bytes=16384)` — pass an OTel
logger (`flanj.otlp_logger()` or your own provider's) or the sinks.
