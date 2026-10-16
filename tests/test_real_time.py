"""The default timers, clocks and event loop, with no fakes and no timing races.

Nothing here asserts that something happens within a deadline: waits are either long
enough never to elapse during the test, or the test blocks on an event (with a generous
safety timeout) until the run it expects has happened.
"""

from __future__ import annotations

import asyncio
import threading

from throttlebounce import async_debounce, async_throttle, debounce, throttle

_SAFETY = 30.0


def test_debounce_runs_on_a_real_timer_thread() -> None:
    done = threading.Event()
    seen: list[tuple[int, bool]] = []

    @debounce(0.01)
    def record(value: int) -> None:
        seen.append((value, threading.current_thread() is threading.main_thread()))
        done.set()

    record(1)
    assert done.wait(_SAFETY)
    assert seen == [(1, False)]
    assert record.pending is False


def test_a_pending_real_timer_never_blocks_and_flush_runs_it_at_once() -> None:
    seen: list[int] = []

    @debounce(3600.0)
    def record(value: int) -> int:
        seen.append(value)
        return value

    record(7)
    assert seen == []
    assert record.flush() == 7
    assert seen == [7]


def test_throttle_trailing_runs_on_a_real_timer() -> None:
    done = threading.Event()
    seen: list[int] = []

    @throttle(0.01, trailing=True)
    def record(value: int) -> int:
        seen.append(value)
        if value == 3:
            done.set()
        return value

    assert record(1) == 1
    record(2)
    record(3)
    assert done.wait(_SAFETY)
    assert seen[0] == 1 and seen[-1] == 3


def test_concurrent_callers_get_exactly_one_leading_run() -> None:
    runs: list[int] = []
    start = threading.Barrier(12)

    @debounce(3600.0, leading=True)
    def record(value: int) -> None:
        runs.append(value)

    def hammer() -> None:
        start.wait()
        for _ in range(200):
            record(threading.get_ident())

    threads = [threading.Thread(target=hammer) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(runs) == 1
    assert record.pending is True
    record.flush()
    assert len(runs) == 2
    assert record.pending is False


def test_concurrent_callers_get_exactly_one_throttled_run() -> None:
    runs: list[int] = []
    start = threading.Barrier(12)

    @throttle(3600.0, trailing=True)
    def record(value: int) -> int:
        runs.append(value)
        return value

    def hammer() -> None:
        start.wait()
        for _ in range(200):
            record(1)

    threads = [threading.Thread(target=hammer) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert runs == [1]
    assert record.flush() == 1
    assert runs == [1, 1]
    record.cancel()


def test_async_wrappers_run_on_the_real_event_loop() -> None:
    async def main() -> tuple[list[int], int | None]:
        done = asyncio.Event()
        seen: list[int] = []

        @async_debounce(0.01)
        async def push(value: int) -> int:
            seen.append(value)
            done.set()
            return value

        @async_throttle(3600.0)
        async def beat(value: int) -> int:
            return value

        push(1)
        push(2)
        await asyncio.wait_for(done.wait(), _SAFETY)
        beat(5)
        beat(6)
        await asyncio.sleep(0)
        return seen, beat.result

    assert asyncio.run(main()) == ([2], 5)
