"""Zero-code entry: ``import flanj.register`` as the FIRST line of your program.

The counterpart of ``node -r @flanj/sdk/register``, filling the same role: one
line and capture is on. It calls :func:`flanj.start` (configured from the
environment), installs :func:`flanj.flush_on_exit`, and auto-instruments every MCP
client session (:func:`flanj.register_mcp_auto_instrumentation`).

That last step is where it differs in form from the TypeScript entry, which
switches on HTTP body capture instead: HTTP capture is the one thing the Python
SDK does not do, and MCP is the whole of what it does. The difference is recorded
in the contract (CONTRACTS section 2).

Load it before anything opens an MCP transport - the same rule as Datadog's
``import ddtrace.auto`` - or the SDK cannot tell which servers are remote.

Environment: ``FLANJ_INTEGRATION_ID`` (else one integration per server, derived
from its host or name), ``OTEL_SERVICE_NAME``, ``FLANJ_OTLP_ENDPOINT`` /
``OTEL_EXPORTER_OTLP_*``, ``FLANJ_BODY_CAP_BYTES``; ``FLANJ_QUIET=1`` silences
the one startup line.
"""

from __future__ import annotations

import os
import sys

from .flush_on_exit import flush_on_exit
from .mcp.auto import register_mcp_auto_instrumentation
from .start import FlanjHandle, start
from .version import __version__

handle: FlanjHandle = start()
flush_on_exit(handle)
patched = register_mcp_auto_instrumentation(
    integration=handle.integration,
    logger=handle.logger,
    body_cap_bytes=handle.body_cap_bytes,
)

if os.environ.get("FLANJ_QUIET") != "1":
    what = (
        "capturing MCP client calls"
        if patched
        else "loaded, but no MCP client package is installed (pip install mcp)"
    )
    integration = handle.integration or "one per server"
    print(
        f"[flanj] flanj {__version__} {what} -> {handle.endpoint} (integration={integration}). "
        f"Set FLANJ_QUIET=1 to silence this line.",
        file=sys.stderr,
    )
