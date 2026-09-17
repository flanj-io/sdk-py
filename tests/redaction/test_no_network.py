"""ZERO-EXTERNAL-CALLS sentinel.

The floor must never do I/O: it runs on every captured body, before anything is
stored or transmitted, inside the customer's process. This test arms a sentinel on
every socket / DNS / subprocess primitive, runs the ENTIRE fixture battery through
both entry points plus the enhancer, and fails if anything was touched.

The TypeScript package arms ``http``/``https``/``net``/``dns``/``child_process``/
``fetch``; this is the same set in Python. The filesystem is covered statically
instead, by ``test_import_hygiene.py`` - the same division of labour the TypeScript
side has between this sentinel and its ESLint ``no-restricted-imports`` ban.
"""

from __future__ import annotations

import os
import socket
import subprocess
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from flanj.redaction import create_redactor, enhance

from ..conftest import FIXTURES, VECTORS, js_json

_TARGETS: list[tuple[Any, str]] = [
    (socket, "socket"),
    (socket, "create_connection"),
    (socket, "getaddrinfo"),
    (socket, "gethostbyname"),
    (subprocess, "Popen"),
    (subprocess, "run"),
    (os, "system"),
    (os, "popen"),
    (urllib.request, "urlopen"),
]


@pytest.fixture()
def sentinel() -> Iterator[list[str]]:
    calls: list[str] = []
    originals: list[Callable[[], None]] = []

    def arm(obj: Any, name: str) -> None:
        original = getattr(obj, name)
        label = f"{getattr(obj, '__name__', obj)}.{name}"

        def tripped(*args: Any, **kwargs: Any) -> Any:
            calls.append(label)
            raise AssertionError(f"network sentinel: {label} called from the redaction floor")

        setattr(obj, name, tripped)
        originals.append(lambda: setattr(obj, name, original))

    # Warm the validators' lazily-imported metadata BEFORE arming: `phonenumbers`
    # imports its region metadata on first use, and an import is not a socket call
    # - but warming keeps the failure surface to the battery itself.
    from flanj.redaction.validators import is_valid_phone_number

    is_valid_phone_number("+14155552671")

    for obj, name in _TARGETS:
        arm(obj, name)
    try:
        yield calls
    finally:
        for restore in originals:
            restore()


def test_every_fixture_and_vector_through_both_entry_points_touches_no_network(
    sentinel: list[str],
) -> None:
    redactor = create_redactor(include_ip=True)
    for case in FIXTURES["cases"]:
        if case["kind"] == "json":
            redactor.redact(case["input"])
            redactor.redact_text(js_json(case["input"]))
            if case.get("enhancer"):
                enhance(redactor.redact(case["input"]).redacted, case["enhancer"]["spec"])
        else:
            redactor.redact_text(case["input"])
    for vector in VECTORS["cases"]:
        redactor.redact_text(vector["input"])
    assert sentinel == []


def test_the_sentinel_itself_trips(sentinel: list[str]) -> None:
    """A sentinel that cannot fire proves nothing - prove it fires."""
    with pytest.raises(AssertionError, match="network sentinel"):
        socket.getaddrinfo("example.com", 443)
    assert sentinel == ["socket.getaddrinfo"]
