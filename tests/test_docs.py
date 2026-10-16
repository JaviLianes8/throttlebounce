"""Every Python example and command line transcript in README and GUIDE holds.

The examples use the real default timers; ``threading.Timer`` is replaced by one that
never fires on its own, so an example that relies on ``flush()`` cannot race a timer
on a slow machine.
"""

from __future__ import annotations

import io
import re
import shlex
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from throttlebounce._cli import main

ROOT = Path(__file__).resolve().parents[1]
DOCS = {name: (ROOT / name).read_text(encoding="utf-8") for name in ("README.md", "GUIDE.md")}
PYTHON = [
    (n, b) for n, text in DOCS.items() for b in re.findall(r"```python\n(.*?)```", text, re.S)
]
CONSOLE = [
    (n, b) for n, text in DOCS.items() for b in re.findall(r"```console\n(.*?)```", text, re.S)
]


class _Parked:
    def __init__(self, delay: float, action: Callable[[], None]) -> None:
        self.daemon = False
        self.ident = None  # never started, as far as anyone waiting on it can tell

    def start(self) -> None:
        pass

    def cancel(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _parked_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(threading, "Timer", _Parked)


def test_both_documents_have_examples() -> None:
    assert {n for n, _ in PYTHON} == {n for n, _ in CONSOLE} == set(DOCS)


@pytest.mark.parametrize(("name", "block"), PYTHON)
def test_python_example_runs(name: str, block: str) -> None:
    exec(compile(block, name, "exec"), {"__name__": "example"})


@pytest.mark.parametrize(("name", "block"), CONSOLE)
def test_console_transcript_matches(
    name: str, block: str, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    command, _, expected = block.partition("\n")
    feed, _, invocation = command.removeprefix("$ ").partition(" | ")
    lines = shlex.split(feed)[1].encode().decode("unicode_escape")
    argv = shlex.split(invocation)
    assert argv[0] == "throttlebounce"
    argv = [sys.executable if part == "python" else part for part in argv[1:]]
    monkeypatch.setattr(sys, "stdin", io.StringIO(lines))
    assert main(argv) == 0
    assert capfd.readouterr().out.replace("\r\n", "\n") == expected
