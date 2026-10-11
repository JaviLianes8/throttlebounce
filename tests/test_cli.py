"""Tests for the CLI argument handling and a real (non-mocked) command run."""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import pytest

from throttlebounce._cli import _split_command, main


def test_split_command_separates_options_from_the_command() -> None:
    options, command = _split_command(["debounce", "--wait", "0.5", "--", "make", "build"])
    assert options == ["debounce", "--wait", "0.5"]
    assert command == ["make", "build"]


def test_split_command_without_a_separator_has_no_command() -> None:
    options, command = _split_command(["throttle", "--interval", "1"])
    assert options == ["throttle", "--interval", "1"]
    assert command == []


def test_a_missing_command_is_an_error() -> None:
    with pytest.raises(SystemExit):
        main(["debounce", "--wait", "0.5"])


def test_no_trailing_without_leading_is_an_error() -> None:
    with pytest.raises(SystemExit):
        main(["debounce", "--wait", "0.5", "--no-trailing", "--", "true"])


def test_main_debounces_a_real_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    marker = tmp_path / "runs.txt"
    code = f"open({str(marker)!r}, 'a', encoding='utf-8').write('x')"
    monkeypatch.setattr(sys, "stdin", io.StringIO("a\nb\nc\n"))
    exit_code = main(["debounce", "--wait", "0.2", "--", sys.executable, "-c", code])
    assert exit_code == 0
    time.sleep(0.05)
    assert marker.read_text(encoding="utf-8") == "x"
