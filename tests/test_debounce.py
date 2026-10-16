"""Behaviour tests for the debounce decorator, with a fake timer (no real waits)."""

from __future__ import annotations

import pytest
from _fakes import TimerSpy

from throttlebounce import debounce


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


def test_leading_edge_fires_on_the_first_call_of_a_burst() -> None:
    spy = TimerSpy()
    seen: list[int] = []

    @debounce(0.5, leading=True, trailing=False, timer_factory=spy)
    def record(value: int) -> None:
        seen.append(value)

    record(1)
    assert seen == [1]
    record(2)
    record(3)
    assert seen == [1]
    spy.timers[-1].fire()
    assert seen == [1]
    record(4)
    assert seen == [1, 4]


def test_both_edges_run_leading_then_trailing_only_when_more_than_one_call() -> None:
    spy = TimerSpy()
    seen: list[int] = []

    @debounce(0.5, leading=True, trailing=True, timer_factory=spy)
    def record(value: int) -> None:
        seen.append(value)

    record(1)
    record(2)
    record(3)
    assert seen == [1]
    spy.timers[-1].fire()
    assert seen == [1, 3]


def test_both_edges_with_a_lone_call_does_not_run_trailing() -> None:
    spy = TimerSpy()
    seen: list[int] = []

    @debounce(0.5, leading=True, trailing=True, timer_factory=spy)
    def record(value: int) -> None:
        seen.append(value)

    record(1)
    assert seen == [1]
    spy.timers[-1].fire()
    assert seen == [1]


def test_max_wait_forces_a_run_during_an_unbroken_burst() -> None:
    spy = TimerSpy()
    seen: list[int] = []

    @debounce(0.5, max_wait=1.0, timer_factory=spy)
    def record(value: int) -> None:
        seen.append(value)

    record(1)
    deadline = next(t for t in spy.timers if t.delay == 1.0)
    record(2)
    record(3)
    assert seen == []
    deadline.fire()
    assert seen == [3]


def test_result_exposes_the_last_value_without_forcing_a_run() -> None:
    spy = TimerSpy()

    @debounce(0.5, timer_factory=spy)
    def double(value: int) -> int:
        return value * 2

    assert double.result is None
    double(21)
    spy.timers[-1].fire()
    assert double.result == 42


def test_both_edges_off_is_rejected() -> None:
    with pytest.raises(ValueError):
        debounce(0.5, leading=False, trailing=False)


def test_a_negative_max_wait_is_rejected() -> None:
    with pytest.raises(ValueError):
        debounce(0.5, max_wait=-1.0)
