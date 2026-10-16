"""Timers: the delays requested, stale timers ignored, nothing left scheduled, no deadlock."""

from __future__ import annotations

from _fakes import FakeClock, TimerSpy
from _virtual import VirtualTime

from throttlebounce import debounce, throttle


def test_a_replaced_timer_that_fires_late_is_ignored() -> None:
    spy = TimerSpy()
    seen: list[int] = []
    record = debounce(1, timer_factory=spy)(seen.append)
    record(1)
    record(2)
    spy.timers[0].action()  # the first quiet timer, already replaced, fires anyway
    assert seen == []
    assert record.pending is True
    spy.timers[-1].fire()
    assert seen == [2]


def test_a_cancelled_throttle_timer_that_fires_late_is_ignored() -> None:
    spy, clock = TimerSpy(), FakeClock()
    seen: list[int] = []
    record = throttle(1, trailing=True, clock=clock, timer_factory=spy)(seen.append)
    record(1)
    record(2)
    record.cancel()
    record(3)
    spy.timers[0].action()
    assert seen == [1]
    assert spy.timers[-1].delay == 1


def test_timer_delays_are_the_wait_the_deadline_and_the_rest_of_the_window() -> None:
    spy, clock = TimerSpy(), FakeClock()
    debounce(2, max_wait=5, timer_factory=spy)(print)("x")
    assert sorted(t.delay for t in spy.timers) == [2, 5]
    spy.timers.clear()
    record = throttle(4, trailing=True, clock=clock, timer_factory=spy)(lambda: None)
    record()
    clock.advance(1.5)
    record()
    assert [t.delay for t in spy.timers] == [2.5]


def test_a_timer_that_fires_inside_start_does_not_deadlock() -> None:
    class Immediate:
        def __init__(self, delay: float, action: object) -> None:
            self.action = action

        def start(self) -> None:
            self.action()  # type: ignore[operator]

        def cancel(self) -> None:
            pass

    seen: list[int] = []
    debounce(1, timer_factory=Immediate)(seen.append)(1)
    clock = FakeClock()
    gate = throttle(1, trailing=True, clock=clock, timer_factory=Immediate)(seen.append)
    gate(2)
    gate(3)
    assert seen == [1, 2, 3]


def test_nothing_stays_scheduled_once_a_burst_ends() -> None:
    time = VirtualTime()
    seen: list[int] = []
    record = debounce(1, max_wait=5, timer_factory=time.timer_factory)(seen.append)
    record(1)
    time.advance(0.5)
    record(2)
    time.advance(2)  # the burst ended at 1.5, well before the 5 s deadline
    assert (seen, time.queued()) == ([2], 0)
    for stop in (record.cancel, record.flush):
        record(3)
        assert time.queued() == 2
        stop()
        assert time.queued() == 0
    gate = throttle(1, trailing=True, clock=time.clock, timer_factory=time.timer_factory)(
        seen.append
    )
    gate(4)
    gate(5)
    time.advance(20)
    assert time.queued() == 0
    gate(6)
    gate(7)
    assert time.queued() == 1
    gate.flush()
    assert time.queued() == 0
