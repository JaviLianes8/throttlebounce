"""The command line in-process: argument handling, exit status and a real command run."""

from __future__ import annotations

import io
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from throttlebounce._cli import _split_command, main


def _code(marker: Path, status: int = 0) -> list[str]:
    script = f"open({str(marker)!r}, 'a', encoding='utf-8').write('x'); raise SystemExit({status})"
    return [sys.executable, "-c", script]


def _stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


def test_split_command_separates_options_from_the_command() -> None:
    options, command = _split_command(["debounce", "--wait", "0.5", "--", "make", "--", "x"])
    assert options == ["debounce", "--wait", "0.5"]
    assert command == ["make", "--", "x"]


def test_split_command_without_a_separator_has_no_command() -> None:
    assert _split_command(["throttle", "--interval", "1"]) == (["throttle", "--interval", "1"], [])


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["debounce", "--wait", "0.5"], "a command is required"),
        (["debounce", "--wait", "0.5", "--no-trailing", "--", "x"], "--no-trailing needs"),
        (["debounce", "--wait", "-1", "--", "x"], "wait must be between"),
        (["debounce", "--wait", "nan", "--", "x"], "wait must be between"),
        (["debounce", "--wait", "2", "--max-wait", "1", "--", "x"], "at least wait"),
        (["throttle", "--interval", "inf", "--", "x"], "interval must be between"),
        (["throttle", "--interval", "soon", "--", "x"], "invalid float value"),
        ([], "the following arguments are required"),
    ],
)
def test_usage_errors_exit_2_with_a_short_message(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as caught:
        main(argv)
    assert caught.value.code == 2
    err = capsys.readouterr().err
    assert message in err
    assert "Traceback" not in err


def test_a_burst_runs_the_command_once_and_the_exit_status_is_that_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / "runs.txt"
    _stdin(monkeypatch, "a\nb\nc\n")
    assert main(["debounce", "--wait", "3600", "--", *_code(marker, 3)]) == 3
    assert marker.read_text(encoding="utf-8") == "x"


def test_leading_and_trailing_runs_both_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / "runs.txt"
    _stdin(monkeypatch, "a\nb\nc\n")
    assert main(["debounce", "--wait", "3600", "--leading", "--", *_code(marker)]) == 0
    assert marker.read_text(encoding="utf-8") == "xx"


def test_throttle_runs_the_first_trigger_and_with_trailing_the_last(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / "runs.txt"
    _stdin(monkeypatch, "a\nb\nc\n")
    assert main(["throttle", "--interval", "3600", "--", *_code(marker)]) == 0
    assert marker.read_text(encoding="utf-8") == "x"
    _stdin(monkeypatch, "a\nb\nc\n")
    assert main(["throttle", "--interval", "3600", "--trailing", "--", *_code(marker)]) == 0
    assert marker.read_text(encoding="utf-8") == "xxx"


def test_no_input_never_runs_the_command_and_exits_0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / "runs.txt"
    _stdin(monkeypatch, "")
    assert main(["debounce", "--wait", "1", "--", *_code(marker, 5)]) == 0
    assert not marker.exists()


def test_a_command_that_cannot_start_exits_127(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stdin(monkeypatch, "a\n")
    missing = str(tmp_path / "no-such-program")
    assert main(["debounce", "--wait", "3600", "--", missing]) == 127
    assert "cannot run" in capsys.readouterr().err


def test_an_interrupt_drops_the_pending_run_and_exits_130(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def interrupted() -> Iterator[str]:
        yield "a"
        yield "b"
        raise KeyboardInterrupt

    marker = tmp_path / "runs.txt"
    monkeypatch.setattr(sys, "stdin", interrupted())
    assert main(["debounce", "--wait", "3600", "--", *_code(marker)]) == 130
    assert not marker.exists()
