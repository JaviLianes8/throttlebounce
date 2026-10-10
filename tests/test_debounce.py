"""Behaviour tests for the debounce decorator, with a fake timer (no real waits)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from debounce import debounce


class FakeTimer:
    """A one-shot timer that fires only when the test tells it to."""

    def __init__(self, delay: float, action: Callable[[], None]) -> None:
        self.delay = delay
        self.action = action
        self.cancelled = False

    def start(self) -> None:
        pass

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.action()


class TimerSpy:
    """Records every timer it builds so a test can fire the live one."""

    def __init__(self) -> None:
        self.timers: list[FakeTimer] = []

    def __call__(self, delay: float, action: Callable[[], None]) -> FakeTimer:
        timer = FakeTimer(delay, action)
        self.timers.append(timer)
        return timer


def test_rapid_calls_collapse_into_one_run_with_the_last_arguments() -> None:
    spy = TimerSpy()
    seen: list[int] = []

    @debounce(0.5, timer_factory=spy)
    def record(value: int) -> None:
        seen.append(value)

    record(1)
    record(2)
    record(3)
    assert seen == []
    spy.timers[-1].fire()
    assert seen == [3]


def test_every_earlier_timer_is_cancelled() -> None:
    spy = TimerSpy()

    @debounce(0.5, timer_factory=spy)
    def noop() -> None:
        pass

    noop()
    noop()
    noop()
    assert [t.cancelled for t in spy.timers] == [True, True, False]


def test_the_delay_is_passed_to_the_timer() -> None:
    spy = TimerSpy()

    @debounce(0.25, timer_factory=spy)
    def noop() -> None:
        pass

    noop()
    assert spy.timers[0].delay == 0.25


def test_cancel_drops_the_pending_call() -> None:
    spy = TimerSpy()
    seen: list[int] = []

    @debounce(0.5, timer_factory=spy)
    def record(value: int) -> None:
        seen.append(value)

    record(1)
    record.cancel()
    spy.timers[-1].fire()
    assert seen == []
    assert record.pending is False


def test_flush_runs_the_pending_call_now_and_returns_its_result() -> None:
    spy = TimerSpy()

    @debounce(0.5, timer_factory=spy)
    def double(value: int) -> int:
        return value * 2

    double(21)
    assert double.pending is True
    assert double.flush() == 42
    assert double.pending is False


def test_flush_with_nothing_pending_returns_none() -> None:
    spy = TimerSpy()

    @debounce(0.5, timer_factory=spy)
    def identity(value: int) -> int:
        return value

    assert identity.flush() is None


def test_a_negative_wait_is_rejected() -> None:
    with pytest.raises(ValueError):
        debounce(-1.0)
