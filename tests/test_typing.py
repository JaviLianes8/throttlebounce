"""A strict type-checked client: decorated functions and methods keep their signatures."""

from __future__ import annotations

from pathlib import Path

import pytest

api = pytest.importorskip("mypy.api")

CLIENT = """
import asyncio
from throttlebounce import async_debounce, async_throttle, debounce, throttle

@debounce(1.0)
def save(text: str) -> int:
    return len(text)

class Editor:
    @debounce(1.0)
    def save(self, text: str) -> int:
        return len(text)

    @throttle(1.0)
    def ping(self, n: int) -> int:
        return n

    @async_debounce(1.0)
    async def push(self, value: int) -> int:
        return value

    @async_throttle(1.0)
    async def beat(self, value: int) -> int:
        return value

e = Editor()
save("ok")
e.save("ok")
reveal_type(e.ping(1))
reveal_type(e.save.flush())
save(1)  # E1
e.save(1)  # E2
e.save("a", "b")  # E3
e.ping("x")  # E4
e.push("x")  # E5
e.beat(1, 2)  # E6
"""


def test_strict_client_sees_the_real_signatures(tmp_path: Path) -> None:
    client = tmp_path / "client.py"
    client.write_text(CLIENT, encoding="utf-8")
    out, _, status = api.run(["--strict", "--no-incremental", str(client)])
    assert status == 1
    lines = out.splitlines()
    assert sum("Revealed type is" in line and "int | None" in line for line in lines) == 2
    for number in range(1, 7):
        line = next(i for i, text in enumerate(CLIENT.splitlines(), 1) if f"# E{number}" in text)
        assert any(f"client.py:{line}: error" in text for text in lines), (number, out)
    assert sum(": error" in text for text in lines) == 6, out
