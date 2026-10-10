"""Behaviour tests for the throttle decorator, with a fake clock (no real waits)."""

from __future__ import annotations

import pytest

from throttlebounce import throttle


class FakeClock:
    """A clock the test advances by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_the_first_call_runs_immediately() -> None:
    clock = FakeClock()
    calls: list[int] = []

    @throttle(1.0, clock=clock)
    def record(value: int) -> int:
        calls.append(value)
        return value

    assert record(1) == 1
    assert calls == [1]


def test_calls_within_the_interval_are_skipped() -> None:
    clock = FakeClock()
    calls: list[int] = []

    @throttle(1.0, clock=clock)
    def record(value: int) -> None:
        calls.append(value)

    record(1)
    clock.advance(0.4)
    record(2)
    clock.advance(0.4)
    record(3)
    assert calls == [1]


def test_a_call_after_the_interval_runs_again() -> None:
    clock = FakeClock()
    calls: list[int] = []

    @throttle(1.0, clock=clock)
    def record(value: int) -> None:
        calls.append(value)

    record(1)
    clock.advance(1.0)
    record(2)
    assert calls == [1, 2]


def test_a_skipped_call_returns_the_last_result() -> None:
    clock = FakeClock()

    @throttle(1.0, clock=clock)
    def double(value: int) -> int:
        return value * 2

    assert double(10) == 20
    clock.advance(0.5)
    assert double(999) == 20


def test_reset_lets_the_next_call_fire_immediately() -> None:
    clock = FakeClock()
    calls: list[int] = []

    @throttle(1.0, clock=clock)
    def record(value: int) -> None:
        calls.append(value)

    record(1)
    record.reset()
    record(2)
    assert calls == [1, 2]


def test_a_negative_interval_is_rejected() -> None:
    with pytest.raises(ValueError):
        throttle(-1.0)
