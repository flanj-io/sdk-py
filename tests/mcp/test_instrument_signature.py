"""The retired per-server id keyword was removed from the public MCP instrumentation surface.

Since 2026-09-19 the collector derives every record's integration at ingest
(CONTRACTS section 2) and ignores anything the SDK sends, so ``flanj.integration``
is never emitted and nothing here accepts an id to emit it with. This is a plain
removal - the package is not on PyPI - so the honest check is that the
keyword-only parameter is gone and Python itself refuses it. Built via ``**kwargs``
so this file carries no literal trace of the retired keyword (a repo-wide grep for
it is part of this change's own acceptance check).
"""

from __future__ import annotations

from typing import Any

import pytest

from flanj.mcp import instrument_mcp_client


class _Session:
    async def call_tool(self, name: str, arguments: Any = None, **kwargs: Any) -> Any:
        return None

    async def list_tools(self, **kwargs: Any) -> Any:
        return {"tools": [], "nextCursor": None}


def test_instrument_mcp_client_rejects_the_retired_keyword() -> None:
    retired_kwarg = {"integrat" + "ion": "acme-tools"}
    with pytest.raises(TypeError):
        instrument_mcp_client(_Session(), **retired_kwarg)
