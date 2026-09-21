"""The shared redact-at-source assembler: ``route`` is the path, ``target`` is path+query.

CONTRACTS section 2: ``flanj.http.route`` is the path ("templated if known ... else
path"), ``flanj.http.target`` is the redacted path+query. They used to be the same
string, so every distinct query string was a distinct route.

This SDK's only caller today is the MCP assembler, which hands in ``/<tool.name>``
and no query string. The rule is pinned here anyway, case for case with the
TypeScript SDK's ``assemble-call.spec.ts``: the two assemblers are one design, and a
capture path added later must find the rule already in place.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from flanj.assemble_call import assemble_captured_call
from flanj.captured_call import CapturedCall, Correlation
from flanj.mcp.assemble_call import assemble_mcp_call

PAN = "4111111111111111"
EMAIL = "jane@acme.test"


def assemble(**overrides: Any) -> CapturedCall:
    inputs: dict[str, Any] = {
        "direction": "client",
        "peer_host": "api.acme.test",
        "edge_class": "external",
        "capture_bodies": True,
        "method": "POST",
        "protocol": "https:",
        "host": "api.acme.test",
        "path": "/v1/charges",
        "status_code": 422,
        "req_body_raw": "",
        "req_body_truncated": False,
        "res_body_raw": "",
        "res_body_truncated": False,
        "request_headers": {},
        "response_headers": {},
        "correlation": Correlation(),
        "duration_ms": 12,
    }
    inputs.update(overrides)
    return assemble_captured_call(**inputs)


def test_drops_the_query_string_from_route_and_keeps_it_in_target() -> None:
    call = assemble(path="/v1/accounts/acct_1/balance?fields=all")

    assert call.route == "/v1/accounts/acct_1/balance"
    assert call.target == "/v1/accounts/acct_1/balance?fields=all"
    assert call.url_full == "https://api.acme.test/v1/accounts/acct_1/balance?fields=all"


def test_leaves_a_path_with_no_query_string_as_it_was_route_equals_target() -> None:
    call = assemble(path="/v1/charges")

    assert call.route == "/v1/charges"
    assert call.target == "/v1/charges"


def test_stops_at_a_fragment_too_whichever_delimiter_comes_first() -> None:
    assert assemble(path="/v1/docs#intro").route == "/v1/docs"
    assert assemble(path="/v1/docs?page=2#intro").route == "/v1/docs"
    assert assemble(path="/v1/docs#intro?page=2").route == "/v1/docs"


def test_still_reports_a_pattern_that_fired_only_in_the_query_string_target_carries_it() -> None:
    call = assemble(path=f"/v1/accounts/acct_1/balance?notify={EMAIL}")

    assert call.route == "/v1/accounts/acct_1/balance"
    assert call.target == "/v1/accounts/acct_1/balance?notify=⟦REDACTED:EMAIL⟧"
    assert call.redaction_patterns == ["EMAIL"]
    assert call.redaction_applied is True
    assert EMAIL not in json.dumps(asdict(call), ensure_ascii=False)


def test_keeps_a_redaction_that_fired_in_the_path_itself() -> None:
    call = assemble(path=f"/v1/cards/{PAN}?expand=owner")

    assert call.route == "/v1/cards/⟦REDACTED:PAN⟧"
    assert call.target == "/v1/cards/⟦REDACTED:PAN⟧?expand=owner"
    assert call.redaction_patterns == ["PAN"]


def test_never_shows_in_route_a_value_that_target_redacted() -> None:
    # Why the cut comes AFTER redaction. The floor tokenises this value only when a
    # query string sits beside it; redacting a pre-cut path would hand `route` the
    # raw `123` that `target` hid. A slice of the redacted target cannot.
    call = assemble(path="/v1/pay/cvv=123?x=1")

    assert call.target == "/v1/pay/cvv=⟦REDACTED:CVV⟧?x=1"
    assert call.route == "/v1/pay/cvv=⟦REDACTED:CVV⟧"
    assert "123" not in call.route
    assert call.target.startswith(call.route)


def test_gives_an_empty_path_the_root_route_never_an_empty_string() -> None:
    assert assemble(path="?fields=all").route == "/"
    assert assemble(path="").route == "/"
    assert assemble(path="?fields=all").target == "?fields=all"


def test_takes_an_opaque_path_whole_a_question_mark_or_hash_in_a_name_is_not_a_query() -> None:
    call = assemble(path="/what?now#then", opaque_path=True)

    assert call.route == "/what?now#then"
    assert call.target == "/what?now#then"


def test_mcp_route_and_target_are_both_the_tool_name_for_every_name() -> None:
    # CONTRACTS section 2: route = target = "/<tool.name>". The HTTP rule cuts `route`
    # at the query string; a tool name is opaque, so nothing in it is ever a query.
    for tool_name in ("create_refund", "what?now", "c#_lint", "a?b#c"):
        captured = assemble_mcp_call(
            peer_host="mcp.acme.test",
            edge_class="external",
            server_kind="streamable-http",
            tool_name=tool_name,
            args=None,
            result=None,
            is_error=False,
            duration_ms=5,
        )

        assert captured.call.route == f"/{tool_name}"
        assert captured.call.target == f"/{tool_name}"
