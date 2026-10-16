"""CLI contracts added after the blind mutation round."""

from __future__ import annotations

import io
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from throttlebounce._cli import _Runner, main


def test_cli_timers_are_tracked_until_they_finish() -> None:
    runner = _Runner(["x"])
    timers = [runner.timer(3600, lambda: None) for _ in range(70)]
    assert all(t in runner._timers for t in timers)


def test_cli_accepts_leading_without_trailing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("a\nb\n"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0))
    assert main(["debounce", "--wait", "3600", "--leading", "--no-trailing", "--", "x"]) == 0


def test_cli_interrupt_cancels_the_pending_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[Any] = []

    class Recorded(threading.Timer):
        def __init__(self, delay: float, action: Callable[[], None]) -> None:
            super().__init__(delay, action)
            created.append(self)

    def lines() -> Iterator[str]:
        yield "a"
        raise KeyboardInterrupt

    monkeypatch.setattr(threading, "Timer", Recorded)
    monkeypatch.setattr(sys, "stdin", lines())
    assert main(["debounce", "--wait", "3600", "--", "x"]) == 130
    assert created and all(t.finished.is_set() for t in created)


def test_cli_runs_never_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    second_entered = threading.Event()
    overlapped: list[bool] = []

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if not overlapped:
            overlapped.append(second_entered.wait(1))
        else:
            second_entered.set()
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = _Runner(["x"])
    threads = [threading.Thread(target=runner) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert overlapped == [False]
