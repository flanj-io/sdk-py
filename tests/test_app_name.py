"""``_app_name``: the app's own name, resolved from ``sys.modules["__main__"]``.

Literal vectors shared with the TypeScript SDK's equivalent (CONTRACTS section 2,
"Resource attributes"). ``types.SimpleNamespace`` stand-ins for ``__main__`` so no
subprocess is needed to exercise every shape.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import flanj

# `flanj.start` names both the lazily-exported `start()` function (PEP 562,
# `flanj/__init__.py`) and the submodule that defines it. Touching the ATTRIBUTE
# here - before anything imports the submodule directly - resolves it through the
# package's `__getattr__`, which imports the submodule and then self-corrects the
# package attribute back to the callable. A bare `from flanj.start import _app_name`
# skips that self-correction and would permanently leave `flanj.start` bound to the
# module instead of the function for the rest of the process - the trap
# `flanj/__init__.py` documents ("Load flanj first" / lazy exports), just hit from
# the test side instead of the app side.
_ = flanj.start
_app_name = sys.modules["flanj.start"]._app_name


def _main(spec_name: str | None = None, file: str | None = None) -> Any:
    ns = types.SimpleNamespace()
    if spec_name is not None:
        ns.__spec__ = types.SimpleNamespace(name=spec_name)
    if file is not None:
        ns.__file__ = file
    return ns


def test_module_run_spec_strips_trailing_dunder_main() -> None:
    assert _app_name(_main(spec_name="myapp.__main__")) == "myapp"


def test_package_submodule_run_keeps_the_dotted_path() -> None:
    assert _app_name(_main(spec_name="pkg.cli")) == "pkg.cli"


def test_a_bare_dunder_main_spec_is_no_name_even_with_a_file() -> None:
    assert _app_name(_main(spec_name="__main__", file="dir/__main__.py")) is None


def test_a_script_path_gives_its_basename_without_py() -> None:
    assert _app_name(_main(file="/srv/app.py")) == "app"


def test_a_console_script_launcher_gives_its_own_script_name() -> None:
    assert _app_name(_main(file="/venv/bin/gunicorn")) == "gunicorn"


def test_no_spec_and_no_file_gives_no_name() -> None:
    assert _app_name(_main()) is None


def test_main_module_none_gives_no_name() -> None:
    assert _app_name(None) is None
