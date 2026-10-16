"""Ground truth: the same call patterns through lodash, Underscore and throttlebounce.

tests/fixtures/oracle_runs.json holds 1200 seeded scenarios and what lodash 4.18.1 and
Underscore 1.13.8 did with each, run by tests/oracle/run.cjs on a virtual clock (see
scripts/oracle_fixture.py). Every scenario runs here through the sync and the async
wrappers on the same virtual clock.

Two places where lodash differs are known and deliberate, and pinned below: lodash's
throttle with a trailing edge can run twice inside one interval, and its debounce with
``maxWait`` under twice ``wait`` can run a held call after the deadline.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from itertools import zip_longest
from pathlib import Path
from typing import Any

import pytest
from _virtual import run_async, run_sync

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "oracle_runs.json").read_text("utf-8"))
SCENARIOS: list[dict[str, Any]] = FIXTURE["scenarios"]
ORACLE = ROOT / "tests" / "oracle"


def _lodash_throttle_trailing(s: dict[str, Any]) -> bool:
    return s["lib"] == "lodash" and s["kind"] == "throttle" and s["trailing"]


def _lodash_short_deadline(s: dict[str, Any]) -> bool:
    return s["lib"] == "lodash" and s["max_wait"] is not None and s["max_wait"] < 2 * s["wait"]


EXACT = [s for s in SCENARIOS if not _lodash_throttle_trailing(s) and not _lodash_short_deadline(s)]


def _same(s: dict[str, Any], got: dict[str, Any]) -> bool:
    returns_match = s["kind"] == "debounce" or got["returns"] in (None, s["returns"])
    return bool(got["runs"] == s["runs"] and returns_match)


def test_the_fixture_names_the_fetched_sources() -> None:
    manifest = json.loads((ORACLE / "MANIFEST.json").read_text("utf-8"))
    for name, source in FIXTURE["source"].items():
        assert source["sha256"] == manifest[name]["sha256"]
    assert len(SCENARIOS) == 1200
    assert {s["lib"] for s in EXACT} == {"lodash", "underscore"}
    assert len(EXACT) == 992


@pytest.mark.parametrize("runner", [run_sync, run_async], ids=["sync", "async"])
def test_every_shared_option_runs_exactly_like_the_javascript_libraries(runner: Any) -> None:
    differ = [s["id"] for s in EXACT if not _same(s, runner(s))]
    assert differ == []


@pytest.mark.parametrize("runner", [run_sync, run_async], ids=["sync", "async"])
@pytest.mark.parametrize("quirk", [_lodash_throttle_trailing, _lodash_short_deadline])
def test_lodash_differs_only_by_its_slipping_deadline(runner: Any, quirk: Any) -> None:
    # At the first run that differs, either lodash ran inside the interval of the run
    # before it, or throttlebounce ran exactly at the deadline and lodash later.
    cases = [s for s in SCENARIOS if quirk(s)]
    differ = [s for s in cases if not _same(s, runner(s))]
    assert 0 < len(differ) < len(cases)
    for s in differ:
        ours, theirs = runner(s)["runs"], s["runs"]
        i = next(i for i, (a, b) in enumerate(zip_longest(ours, theirs)) if a != b)
        deadline = s["max_wait"] or s["wait"]
        if i < len(theirs) and (i == len(ours) or theirs[i][0] < ours[i][0]):
            assert theirs[i][0] - theirs[i - 1][0] < s["wait"], s["id"]
        else:
            assert ours[i][0] == ours[i - 1][0] + deadline, s["id"]
            assert i == len(theirs) or theirs[i][0] > ours[i][0], s["id"]


def _live_ready() -> bool:
    return shutil.which("node") is not None and (ORACLE / "lodash" / "debounce.js").is_file()


@pytest.mark.skipif(not _live_ready(), reason="run scripts/fetch_oracles.py (needs Node.js)")
def test_the_fixture_is_what_the_libraries_do_today() -> None:
    keys = ("runs", "returns")
    cases = [{k: v for k, v in s.items() if k not in keys} for s in SCENARIOS]
    done = subprocess.run(
        ["node", str(ORACLE / "run.cjs")],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    )
    live = json.loads(done.stdout)
    assert all({k: s[k] for k in keys} == live[s["id"]] for s in SCENARIOS)
