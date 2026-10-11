"""The complete promise, measured with real clocks and real threads (no fakes).

These tests use the default real timers and clocks, so they prove the decorators
behave in wall-clock time, not just against an injected fake. Margins are wide so
the assertions are about ordering and collapsing, never a knife-edge sleep.
"""

from __future__ import annotations

import threading
import time

from throttlebounce import debounce, throttle


def test_debounce_defers_then_runs_in_real_time() -> None:
    seen: list[int] = []

    @debounce(0.2)
    def record(value: int) -> None:
        seen.append(value)

    record(1)
    record(2)
    assert seen == []
    time.sleep(0.45)
    assert seen == [2]


def test_debounce_flush_runs_immediately_without_waiting() -> None:
    seen: list[int] = []

    @debounce(10.0)
    def record(value: int) -> None:
        seen.append(value)

    record(7)
    assert seen == []
    assert record.flush() is None or seen == [7]
    assert seen == [7]
    record.cancel()


def test_throttle_runs_once_per_real_interval() -> None:
    seen: list[int] = []

    @throttle(0.3)
    def record(value: int) -> None:
        seen.append(value)

    record(1)
    record(2)
    assert seen == [1]
    time.sleep(0.4)
    record(3)
    assert seen == [1, 3]


def test_debounce_collapses_a_concurrent_storm_without_corruption() -> None:
    runs: list[int] = []
    guard = threading.Lock()

    @debounce(0.1)
    def record(value: int) -> None:
        with guard:
            runs.append(value)

    def hammer() -> None:
        for _ in range(100):
            record(threading.get_ident())

    threads = [threading.Thread(target=hammer) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    time.sleep(0.3)

    # 1200 calls collapsed into a tiny number of real runs, and nothing crashed.
    assert 1 <= len(runs) <= 20
    assert record.pending is False


def test_throttle_is_thread_safe_under_concurrent_calls() -> None:
    runs: list[int] = []
    guard = threading.Lock()

    @throttle(0.1)
    def record(value: int) -> None:
        with guard:
            runs.append(value)

    def hammer() -> None:
        for _ in range(100):
            record(1)

    threads = [threading.Thread(target=hammer) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Leading-edge throttle admits very few runs out of 1200 racing calls.
    assert 1 <= len(runs) <= 20
