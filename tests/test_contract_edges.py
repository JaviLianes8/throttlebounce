"""Edge semantics that the oracle scenarios do not reach: control calls, stale timers,
exceptions, clocks that jump, and the exact timer delays requested."""

from __future__ import annotations

import pytest
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


def test_debounce_cancel_and_flush_end_the_burst() -> None:
    spy = TimerSpy()
    seen: list[int] = []
    record = debounce(1, leading=True, timer_factory=spy)(seen.append)
    record(1)
    record(2)
    record.cancel()
    assert record.pending is False
    record(3)  # a new burst, so the leading edge runs again
    record(4)
    assert record.flush() is None  # list.append returns None
    record(5)
    assert seen == [1, 3, 4, 5]
    assert all(t.cancelled for t in spy.timers[:-1])


def test_trailing_off_keeps_nothing_pending() -> None:
    spy = TimerSpy()
    seen: list[int] = []
    record = debounce(1, leading=True, trailing=False, timer_factory=spy)(seen.append)
    record(1)
    record(2)
    assert record.pending is False
    assert record.flush() is None
    assert seen == [1]


def test_a_deadline_with_trailing_off_opens_a_new_burst_on_the_next_call() -> None:
    time = VirtualTime()
    seen: list[tuple[float, int]] = []
    record = debounce(
        2, leading=True, trailing=False, max_wait=3, timer_factory=time.timer_factory
    )(lambda n: seen.append((time.now, n)))
    for at in range(8):
        time.advance(at)
        record(at)
    time.advance(20)
    assert seen == [(0, 0), (3, 3), (6, 6)]


def test_throttle_cancel_keeps_the_window_and_reset_clears_it() -> None:
    spy, clock = TimerSpy(), FakeClock()
    seen: list[int] = []
    record = throttle(10, trailing=True, clock=clock, timer_factory=spy)(seen.append)
    record(1)
    record(2)
    record.cancel()
    assert record.pending is False
    clock.advance(5)
    record(3)
    assert seen == [1]
    record.reset()
    record(4)
    assert seen == [1, 4]
    assert record.pending is False


def test_throttle_flush_opens_a_new_window() -> None:
    clock = FakeClock()
    seen: list[int] = []
    record = throttle(10, trailing=True, clock=clock, timer_factory=TimerSpy())(seen.append)
    record(1)
    clock.advance(9)
    record(2)
    record.flush()
    clock.advance(2)
    record(3)  # 11 after the first run, but only 2 after the flushed one
    assert seen == [1, 2]
    assert record.pending is True


@pytest.mark.parametrize("jump", [-0.001, -100.0])
def test_a_clock_that_goes_backwards_closes_the_window(jump: float) -> None:
    clock = FakeClock()
    clock.now = 50.0
    seen: list[int] = []
    record = throttle(10, clock=clock)(seen.append)
    record(1)
    clock.advance(jump)
    record(2)
    assert seen == [1, 2]


def test_a_run_that_raises_propagates_and_leaves_the_wrapper_usable() -> None:
    spy, clock = TimerSpy(), FakeClock()

    def fragile(value: int) -> int:
        if value < 0:
            raise RuntimeError("boom")
        return value

    deb = debounce(1, timer_factory=spy)(fragile)
    deb(-1)
    with pytest.raises(RuntimeError):
        deb.flush()
    assert deb.pending is False
    assert deb.result is None
    deb(4)
    with pytest.raises(RuntimeError):
        debounce(1, leading=True, timer_factory=spy)(fragile)(-1)
    spy.timers[-2].fire()
    assert deb.result == 4

    thr = throttle(1, clock=clock)(fragile)
    with pytest.raises(RuntimeError):
        thr(-1)
    assert thr(5) is None  # the failed run still opened the window
    clock.advance(1)
    assert thr(5) == 5


def test_a_zero_wait_still_defers_to_the_timer() -> None:
    spy = TimerSpy()
    seen: list[int] = []
    record = debounce(0, timer_factory=spy)(seen.append)
    record(1)
    assert seen == []
    spy.timers[-1].fire()
    assert seen == [1]
    gate = throttle(0, clock=FakeClock())(seen.append)
    gate(2)
    gate(3)
    assert seen == [1, 2, 3]


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
