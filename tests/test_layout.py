import ast
import importlib
import pathlib
import sys
from unittest.mock import MagicMock

import pytest

ROOT = pathlib.Path(__file__).parents[1]
FORBIDDEN = {"client": {"server"}, "shared": {"server", "client"}, "server": {"client"}}

# hardware scripts that do their work at import (CircuitPython firmware, a serial port, GPIO)
NOT_IMPORTABLE_HERE = {"client.input.aerial_listener", "client.input.uart_bridge", "client.input.cable_box"}


def _modules(package):
    for path in sorted((ROOT / package).rglob("*.py")):
        yield path, ".".join(path.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__")


def _imported_packages(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_each_end_only_imports_what_it_may(package):
    offenders = [f"{module} imports {name}" for path, module in _modules(package)
                 for name in _imported_packages(path) if name in FORBIDDEN[package]]
    assert offenders == []


@pytest.mark.parametrize("package", ["server", "shared", "client"])
def test_every_module_imports(package, monkeypatch):
    for stub in ("ffmpeg", "moviepy", "moviepy.editor", "tkinter", "tkinter.font", "tkinter.ttk", "evdev",
                 "PySide6", "PySide6.QtWidgets", "PySide6.QtGui", "PySide6.QtCore", "PySide6.QtWebEngineWidgets",
                 "PySide6.QtWebEngineCore", "PySide6.QtQuick"):
        monkeypatch.setitem(sys.modules, stub, sys.modules.get(stub) or MagicMock())
    for _, module in _modules(package):
        if module not in NOT_IMPORTABLE_HERE:
            importlib.import_module(module)
