"""Regenerate tests/fixtures/oracle_runs.json from the real lodash and Underscore code.

Needs Node.js and the libraries fetched by scripts/fetch_oracles.py. The scenarios are
generated from a fixed seed; the recorded runs are what the JavaScript libraries did,
so the fixture is program output, not hand-written data.

    python scripts/oracle_fixture.py
"""

from __future__ import annotations

import datetime
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "tests" / "oracle"
FIXTURE = ROOT / "tests" / "fixtures" / "oracle_runs.json"
SEED = 20261016


def _calls(rng: random.Random, wait: int) -> list[int]:
    gaps = [0, 1, wait // 2, wait - 1, wait, wait + 1, 2 * wait, 3 * wait + 7]
    times, now = [], rng.randrange(0, 5)
    for _ in range(rng.randrange(1, 25)):
        times.append(now)
        now += rng.choice(gaps) if rng.random() < 0.5 else rng.randrange(0, 3 * wait + 2)
    return times


def scenarios() -> list[dict[str, Any]]:
    """Every option the two libraries share with throttlebounce, on seeded call patterns."""
    rng = random.Random(SEED)
    out: list[dict[str, Any]] = []
    edges = [(False, True), (True, False), (True, True)]
    for number in range(1200):
        wait = rng.choice([0, 1, 10, 25, 100])
        calls = _calls(rng, max(wait, 1))
        end = calls[-1] + 6 * max(wait, 1) + 10
        leading, trailing = rng.choice(edges)
        base = {"wait": wait, "calls": calls, "end": end}
        if number % 3 == 0:
            spec = {"kind": "debounce", "lib": "underscore", "max_wait": None}
            leading, trailing = rng.choice(edges[:2])
        elif number % 3 == 1:
            factor = rng.choice([None, 1, 1.5, 2, 3, 5])
            max_wait = None if factor is None else int(max(wait, 1) * factor)
            spec = {"kind": "debounce", "lib": "lodash", "max_wait": max_wait}
        else:
            lib = rng.choice(["underscore", "lodash"])
            spec = {"kind": "throttle", "lib": lib, "max_wait": None}
            leading = True
            trailing = rng.random() < 0.5
        out.append(
            {"id": f"s{number:04d}", **base, **spec, "leading": leading, "trailing": trailing}
        )
    return out


def run_node(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the scenarios through tests/oracle/run.cjs and return its output."""
    done = subprocess.run(
        ["node", str(ORACLE / "run.cjs")],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    )
    result: dict[str, Any] = json.loads(done.stdout)
    return result


def main() -> int:
    manifest = json.loads((ORACLE / "MANIFEST.json").read_text(encoding="utf-8"))
    cases = scenarios()
    outputs = run_node(cases)
    node = subprocess.run(["node", "--version"], capture_output=True, text=True, check=True)
    fixture = {
        "source": {
            name: {k: entry[k] for k in ("title", "url", "sha256")}
            for name, entry in manifest.items()
        },
        "node": node.stdout.strip(),
        "recorded": datetime.date.today().isoformat(),
        "seed": SEED,
        "scenarios": [{**case, **outputs[case["id"]]} for case in cases],
    }
    FIXTURE.parent.mkdir(exist_ok=True)
    rows = ",\n".join(json.dumps(row, separators=(",", ":")) for row in fixture.pop("scenarios"))
    head = json.dumps(fixture, indent=1)[:-2]
    FIXTURE.write_text(f'{head},\n "scenarios": [\n{rows}\n]}}\n', encoding="utf-8")
    print(f"{len(cases)} scenarios recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
