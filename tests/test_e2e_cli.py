"""Real end-to-end: install the package into a fresh venv and drive the console script.

Nothing here is mocked. A throwaway virtual environment pip-installs the project in
editable mode, which registers the real ``throttlebounce`` console script, and the
tests then run that script as a subprocess with trigger lines piped to its stdin.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_IS_WINDOWS = os.name == "nt"


@pytest.fixture(scope="module")
def console_script(tmp_path_factory: pytest.TempPathFactory) -> Path:
    env_dir = tmp_path_factory.mktemp("tb_venv")
    venv.create(env_dir, with_pip=True)
    bin_dir = env_dir / ("Scripts" if _IS_WINDOWS else "bin")
    python = bin_dir / ("python.exe" if _IS_WINDOWS else "python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "-e", str(_REPO_ROOT), "-q"],
        check=True,
        timeout=300,
    )
    script = bin_dir / ("throttlebounce.exe" if _IS_WINDOWS else "throttlebounce")
    assert script.is_file(), "the editable install did not register the console script"
    return script


def _counter_command(marker: Path) -> list[str]:
    code = f"open({str(marker)!r}, 'a', encoding='utf-8').write('x')"
    return [sys.executable, "-c", code]


def test_installed_script_reports_its_version(console_script: Path) -> None:
    result = subprocess.run(
        [str(console_script), "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert result.stdout.strip() == "throttlebounce 0.2.0"


def test_installed_script_debounces_a_burst_into_one_run(
    console_script: Path, tmp_path: Path
) -> None:
    marker = tmp_path / "runs.txt"
    command = [str(console_script), "debounce", "--wait", "0.5", "--", *_counter_command(marker)]
    result = subprocess.run(command, input="a\nb\nc\nd\ne\n", text=True, timeout=60)
    assert result.returncode == 0
    assert marker.read_text(encoding="utf-8") == "x"


def test_installed_script_throttle_runs_the_leading_trigger(
    console_script: Path, tmp_path: Path
) -> None:
    marker = tmp_path / "runs.txt"
    command = [str(console_script), "throttle", "--interval", "30", "--", *_counter_command(marker)]
    result = subprocess.run(command, input="a\nb\nc\n", text=True, timeout=60)
    assert result.returncode == 0
    # The first trigger runs at once; the rest fall inside the 30s window.
    assert marker.read_text(encoding="utf-8") == "x"
