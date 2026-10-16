"""Real end-to-end: the installed ``throttlebounce`` console script, driven by subprocess.

When the package is imported from an installed wheel (the suite run from the sdist with
``src`` removed), the script installed next to this interpreter is used; otherwise a
throwaway venv gets an editable install of this checkout. Nothing is mocked, and the
waits are long enough never to elapse: runs come from the edges and the flush at the
end of input.
"""

from __future__ import annotations

import subprocess
import sys
import time
import venv
from pathlib import Path

import pytest

import throttlebounce

_ROOT = Path(__file__).resolve().parents[1]
_WINDOWS = sys.platform == "win32"


@pytest.fixture(scope="session")
def script(tmp_path_factory: pytest.TempPathFactory) -> Path:
    name = "throttlebounce.exe" if _WINDOWS else "throttlebounce"
    bin_name = "Scripts" if _WINDOWS else "bin"
    if _ROOT / "src" not in Path(throttlebounce.__file__).resolve().parents:
        installed = Path(sys.executable).parent / name
        if not installed.is_file():
            installed = Path(sys.prefix) / bin_name / name
        assert installed.is_file(), f"installed console script missing at {installed}"
        return installed
    env = tmp_path_factory.mktemp("tb_venv")
    venv.create(env, with_pip=True)
    python = env / bin_name / ("python.exe" if _WINDOWS else "python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", "-e", str(_ROOT)],
        check=True,
        capture_output=True,
        timeout=600,
    )
    installed = env / bin_name / name
    assert installed.is_file(), "the editable install did not register the console script"
    return installed


def _command(marker: Path, status: int = 0) -> list[str]:
    code = f"open({str(marker)!r}, 'a', encoding='utf-8').write('x'); raise SystemExit({status})"
    return [sys.executable, "-c", code]


def _run(script: Path, args: list[str], stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *args], input=stdin, capture_output=True, text=True, timeout=120
    )


def test_the_script_reports_the_package_version(script: Path) -> None:
    done = _run(script, ["--version"], "")
    assert (done.returncode, done.stdout.strip()) == (
        0,
        f"throttlebounce {throttlebounce.__version__}",
    )


def test_a_burst_of_triggers_runs_the_command_once(script: Path, tmp_path: Path) -> None:
    marker = tmp_path / "runs.txt"
    done = _run(script, ["debounce", "--wait", "3600", "--", *_command(marker, 4)], "a\nb\nc\n")
    assert done.returncode == 4
    assert marker.read_text(encoding="utf-8") == "x"


def test_throttle_runs_the_leading_and_trailing_triggers(script: Path, tmp_path: Path) -> None:
    marker = tmp_path / "runs.txt"
    args = ["throttle", "--interval", "3600", "--trailing", "--", *_command(marker)]
    done = _run(script, args, "a\nb\nc\n")
    assert done.returncode == 0
    assert marker.read_text(encoding="utf-8") == "xx"


def test_a_usage_error_exits_2_without_a_traceback(script: Path) -> None:
    done = _run(script, ["debounce", "--wait", "-1", "--", "x"], "")
    assert done.returncode == 2
    assert "wait must be between" in done.stderr
    assert "Traceback" not in done.stderr


def test_the_command_gets_no_stdin_so_triggers_are_never_swallowed(
    script: Path, tmp_path: Path
) -> None:
    marker = tmp_path / "stdin.txt"
    code = f"import sys; open({str(marker)!r}, 'a').write(str(len(sys.stdin.read())))"
    args = ["throttle", "--interval", "3600", "--", sys.executable, "-c", code]
    with subprocess.Popen([str(script), *args], stdin=subprocess.PIPE, text=True) as proc:
        assert proc.stdin is not None
        proc.stdin.write("a\n")
        proc.stdin.flush()
        # The leading run starts while the pipe is still open: a command that could
        # read our stdin would block here until it closes.
        deadline = time.monotonic() + 60
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        ran_before_eof = marker.exists()
        proc.stdin.write("b\n")
        proc.stdin.close()
        assert proc.wait(timeout=120) == 0
    assert ran_before_eof
    assert marker.read_text() == "0"
