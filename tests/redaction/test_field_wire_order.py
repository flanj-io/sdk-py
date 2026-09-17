"""Byte-exactness of the ``flanj.redaction.fields`` wire record.

The parity battery compares field records by DEEP EQUALITY, and mapping equality
is order-insensitive in Python (and in JavaScript). But this record does not reach
the collector as a mapping - it reaches it as
``JSON.stringify(fields)`` in one attribute string, where key order is bytes.

So the whole battery stays green while the emitted bytes diverge from the Go
collector and the TypeScript SDK. This file closes that hole by pinning the
serialized form. It was written against a defect that really did slip past the
battery: moving ``integer`` out of last place left 506 assertions green.
"""

from __future__ import annotations

import json

from flanj.redaction import create_redactor

redactor = create_redactor()

#: The exact key order the contract fixes: props are ``type, length``, the six
#: ``contains*`` flags, then ``integer`` LAST and only for numbers.
STRING_PROPS_ORDER = [
    "type",
    "length",
    "containsLowerCase",
    "containsUpperCase",
    "containsDigits",
    "containsASCIIControlChars",
    "containsASCIIPrintableChars",
    "containsASCIIExtendedChars",
]
NUMBER_PROPS_ORDER = STRING_PROPS_ORDER + ["integer"]


def _wire(value: object) -> str:
    """Serialize as the SDK does when it builds the OTLP attribute."""
    return json.dumps(redactor.redact(value).fields, ensure_ascii=False, separators=(",", ":"))


def test_string_field_record_serializes_in_contract_order() -> None:
    assert _wire({"card_number": "4111111111111111"}) == (
        '[{"path":"/card_number","pattern":"PAN","props":{"type":"string","length":16,'
        '"containsLowerCase":false,"containsUpperCase":false,"containsDigits":true,'
        '"containsASCIIControlChars":false,"containsASCIIPrintableChars":true,'
        '"containsASCIIExtendedChars":false}}]'
    )


def test_number_field_record_puts_integer_last() -> None:
    assert _wire({"card": 4111111111111111}) == (
        '[{"path":"/card","pattern":"PAN","props":{"type":"number","length":16,'
        '"containsLowerCase":false,"containsUpperCase":false,"containsDigits":true,'
        '"containsASCIIControlChars":false,"containsASCIIPrintableChars":true,'
        '"containsASCIIExtendedChars":false,"integer":true}}]'
    )


def test_props_key_order_is_explicit_not_incidental() -> None:
    string_field = redactor.redact({"card_number": "4111111111111111"}).fields[0]
    number_field = redactor.redact({"card": 4111111111111111}).fields[0]
    assert list(string_field.keys()) == ["path", "pattern", "props"]
    assert list(string_field["props"].keys()) == STRING_PROPS_ORDER
    assert list(number_field["props"].keys()) == NUMBER_PROPS_ORDER
