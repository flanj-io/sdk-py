#!/usr/bin/env bash
#
# A STRANGER'S FIRST RUN.
#
# Build the distribution, install THAT ARTEFACT into a fresh virtualenv with nothing
# of this repo on the path, import it, and drive a real MCP server over a real
# transport. "Green in the repo" is not "works for a stranger": the test suite runs
# against `src/` with the repo's dev dependencies already present, so it cannot see a
# module left out of the wheel, a dependency declared only in the dev extra, or an
# import that happens to resolve because the working directory is the repo root.
#
# The TypeScript SDK has the same script for the same reason. It has caught, there, a
# packaging rule that shipped stale files and an emit option that silently excluded
# sources.
#
# Usage:  bash scripts/smoke-pack.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mSMOKE FAILED: %s\033[0m\n' "$*" >&2; exit 1; }

command -v uv >/dev/null 2>&1 || fail "uv is required (https://docs.astral.sh/uv/)"

say "Building the distribution"
rm -rf "$ROOT/dist"
uv build --out-dir "$ROOT/dist" "$ROOT"
WHEEL="$(ls "$ROOT"/dist/*.whl | head -1)"
[ -n "$WHEEL" ] || fail "no wheel produced"
echo "wheel: $(basename "$WHEEL")"

say "Checking what the wheel actually contains"
python3 - "$WHEEL" <<'PY'
import sys, zipfile
names = zipfile.ZipFile(sys.argv[1]).namelist()
modules = [n for n in names if n.endswith(".py")]
# Every module under src/flanj must be in the wheel. A package left out of
# `[tool.hatch.build.targets.wheel]` imports fine from the repo and ImportErrors for
# everyone else.
required = {"flanj/__init__.py", "flanj/redaction/__init__.py", "flanj/mcp/__init__.py",
            "flanj/redaction/validators/__init__.py", "flanj/redaction/recognizers/__init__.py"}
missing = sorted(required - set(names))
if missing:
    raise SystemExit(f"wheel is missing: {missing}")
# Repo/CI artefacts must NOT ship: contracts and tests are not part of the library.
leaked = sorted(n for n in names if n.startswith(("contracts/", "tests/")))
if leaked:
    raise SystemExit(f"wheel leaks repo artefacts: {leaked}")
print(f"{len(modules)} modules, no contracts/ or tests/ leaked")
PY

say "Installing the wheel into a FRESH venv (nothing of this repo on the path)"
uv venv --python 3.10 "$WORK/venv" >/dev/null
# Install by artefact, not by `-e .`: an editable install would put `src/` back on the
# path and defeat the entire point of this script.
uv pip install --python "$WORK/venv/bin/python" -q "$WHEEL"
uv pip install --python "$WORK/venv/bin/python" -q "mcp>=2.0"

say "Import and redact from the installed package"
cd "$WORK"   # NOT the repo root: a stray `src/` on sys.path would mask a packaging bug
"$WORK/venv/bin/python" - <<'PY'
import flanj, flanj.redaction as floor, pathlib
assert "sdk-py/src" not in str(pathlib.Path(flanj.__file__)), f"resolved to the repo: {flanj.__file__}"
print("flanj", flanj.__version__, "from", flanj.__file__)

out = floor.redact('{"card_number":"4111111111111111","email":"jane@example.com"}')
assert "4111111111111111" not in out and "jane@example.com" not in out, out
assert "⟦REDACTED:PAN⟧" in out and "⟦REDACTED:EMAIL⟧" in out, out
print("redaction floor:", out)
PY

say "Driving a REAL MCP server over a REAL transport"
cat > "$WORK/server.py" <<'PY'
"""A real MCP server over stdio - not a stub, not a mock of the client."""
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("smoke-server")

@mcp.tool()
def get_balance(account_id: str) -> dict:
    """Current balance for an account."""
    # A card number in the payload: the floor must remove it before export.
    return {"account_id": account_id, "amount": 1200, "card_number": "4111111111111111"}

if __name__ == "__main__":
    mcp.run()
PY
cat > "$WORK/drive.py" <<'PY'
# flanj FIRST - before anything imports an MCP transport opener. `from x import y`
# binds the original function, and flanj can only see transports it wrapped.
import flanj

class _NoExport:  # this smoke checks capture, not export; keep stderr clean
    def on_emit(self, record): pass
    emit = on_emit
    def shutdown(self): pass
    def force_flush(self, timeout_millis=30000): return True

# The rule the README states: load flanj BEFORE opening any MCP transport, so it can
# see where each server is. (Skip this line and the session is `unknown`: recorded,
# but without bodies - which is what this smoke caught when that rule was new.)
flanj.start(processor=_NoExport())
from flanj import instrument_mcp_client

import asyncio, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main() -> int:
    captured, snapshots = [], []
    params = StdioServerParameters(command=sys.executable, args=["server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            instrument_mcp_client(
                session, on_capture=captured.append, on_snapshot=snapshots.append
            )
            await session.initialize()
            listed = await session.list_tools()
            names = [t.name for t in listed.tools]
            assert names == ["get_balance"], names
            result = await session.call_tool("get_balance", {"account_id": "acct_1"})

    # The app still got its real result, unmodified.
    payload = str(result.structured_content or result.content)
    assert "4111111111111111" in payload, "the SDK altered the app's own result"

    assert len(snapshots) == 1, f"expected one contract_snapshot, got {len(snapshots)}"
    assert snapshots[0].tool_count == 1
    assert "get_balance" in snapshots[0].snapshot_json

    assert len(captured) == 1, f"expected one captured call, got {len(captured)}"
    call = captured[0]
    assert call.mcp.tool_name == "get_balance"
    assert call.mcp.is_error is False
    assert call.call.edge_class == "local-process", call.call.edge_class
    # THE point of the SDK: the captured copy is redacted, the app's copy is not.
    assert "4111111111111111" not in call.call.response_body, call.call.response_body
    assert "⟦REDACTED:PAN⟧" in call.call.response_body, call.call.response_body
    assert call.call.redaction_patterns == ["PAN"]

    print("snapshot tools:", snapshots[0].tool_count)
    print("captured body :", call.call.response_body)
    print("app's result  : unmodified (still carries the real value)")
    return 0

raise SystemExit(asyncio.run(main()))
PY
"$WORK/venv/bin/python" "$WORK/drive.py"

say "The zero-code entry: import flanj.register, then an app that never calls flanj"
cat > "$WORK/zero_code.py" <<'PY'
import flanj.register  # noqa: F401  - the one line a user adds, first
import asyncio, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main() -> int:
    async with stdio_client(StdioServerParameters(command=sys.executable, args=["server.py"])) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            await s.call_tool("get_balance", {"account_id": "acct_1"})
            assert getattr(s, "__flanj_mcp_instrumented__", False), "the session was not auto-instrumented"
    return 0

raise SystemExit(asyncio.run(main()))
PY
"$WORK/venv/bin/python" "$WORK/zero_code.py" 2> "$WORK/zero_code.err" || { cat "$WORK/zero_code.err"; fail "the zero-code entry failed"; }
grep -q "capturing MCP client calls" "$WORK/zero_code.err" || { cat "$WORK/zero_code.err"; fail "no startup line from flanj.register"; }
echo "flanj.register: session auto-instrumented, startup line printed once"

printf '\n\033[32m==> SMOKE PASSED — the built artefact works for a stranger.\033[0m\n'
