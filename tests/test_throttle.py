"""Behaviour tests for the throttle decorator, with a fake clock (no real waits)."""

from __future__ import annotations

import pytest
from _fakes import FakeClock, TimerSpy

from throttlebounce import throttle


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


def test_trailing_runs_the_last_skipped_call_when_the_window_closes() -> None:
    clock = FakeClock()
    spy = TimerSpy()
    seen: list[int] = []

    @throttle(1.0, trailing=True, clock=clock, timer_factory=spy)
    def record(value: int) -> int:
        seen.append(value)
        return value

    record(1)
    clock.advance(0.3)
    record(2)
    clock.advance(0.3)
    record(3)
    assert seen == [1]
    assert spy.timers[0].delay == pytest.approx(0.7)
    clock.advance(0.4)
    spy.timers[-1].fire()
    assert seen == [1, 3]


def test_trailing_pending_reports_a_waiting_call() -> None:
    clock = FakeClock()
    spy = TimerSpy()

    @throttle(1.0, trailing=True, clock=clock, timer_factory=spy)
    def record(value: int) -> None:
        pass

    record(1)
    assert record.pending is False
    clock.advance(0.3)
    record(2)
    assert record.pending is True


def test_trailing_cancel_drops_the_pending_call() -> None:
    clock = FakeClock()
    spy = TimerSpy()
    seen: list[int] = []

    @throttle(1.0, trailing=True, clock=clock, timer_factory=spy)
    def record(value: int) -> None:
        seen.append(value)

    record(1)
    clock.advance(0.3)
    record(2)
    record.cancel()
    assert record.pending is False
    spy.timers[-1].fire()
    assert seen == [1]


def test_trailing_flush_runs_the_pending_call_now() -> None:
    clock = FakeClock()
    spy = TimerSpy()
    seen: list[int] = []

    @throttle(1.0, trailing=True, clock=clock, timer_factory=spy)
    def record(value: int) -> int:
        seen.append(value)
        return value

    record(1)
    clock.advance(0.3)
    record(2)
    assert record.flush() == 2
    assert record.pending is False
    assert seen == [1, 2]


def test_flush_with_nothing_pending_returns_none() -> None:
    clock = FakeClock()

    @throttle(1.0, clock=clock)
    def identity(value: int) -> int:
        return value

    assert identity.flush() is None


def test_result_exposes_the_last_value() -> None:
    clock = FakeClock()

    @throttle(1.0, clock=clock)
    def double(value: int) -> int:
        return value * 2

    assert double.result is None
    double(21)
    assert double.result == 42
