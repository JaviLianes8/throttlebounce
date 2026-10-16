"""Contracts added after the blind mutation round: each one kills a mutant that survived."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest
from _fakes import FakeClock, FakeScheduler, TimerSpy

from throttlebounce import async_debounce, async_throttle, debounce, throttle


def test_a_flush_with_nothing_pending_does_not_move_the_window() -> None:
    clock = FakeClock()
    seen: list[int] = []
    record = throttle(10, trailing=True, clock=clock, timer_factory=TimerSpy())(seen.append)
    record(1)
    clock.now = 5
    assert record.flush() is None
    clock.now = 12
    record(2)
    assert seen == [1, 2]


def test_the_limits_of_the_options() -> None:
    throttle(threading.TIMEOUT_MAX)
    debounce(threading.TIMEOUT_MAX)
    with pytest.raises(ValueError, match="nothing would ever run"):
        debounce(1, leading=False, trailing=False, max_wait=2)


def test_private_attributes_of_the_function_are_not_copied() -> None:
    def job() -> None:
        pass

    job._private = "no"  # type: ignore[attr-defined]
    assert "_private" not in vars(debounce(1)(job))


def test_bound_copies_keep_every_setting() -> None:
    spy, clock, scheduler = TimerSpy(), FakeClock(), FakeScheduler()

    class Panel:
        @debounce(1, max_wait=5, timer_factory=spy)
        def save(self, n: int) -> None:
            pass

        @throttle(10, trailing=True, clock=clock, timer_factory=spy)
        def show(self, n: int) -> None:
            pass

        @async_debounce(1, scheduler=scheduler)
        async def push(self, n: int) -> None:
            pass

        @async_throttle(10, clock=clock, scheduler=scheduler)
        async def beat(self, n: int) -> int:
            return n

    panel = Panel()
    panel.save(1)
    assert sorted(t.delay for t in spy.timers) == [1, 5]
    panel.show(1)
    panel.show(2)
    assert panel.show.pending is True

    async def main() -> int | None:
        panel.push(1)
        assert len(scheduler.handles) == 1
        panel.beat(1)
        clock.now = 50
        panel.beat(2)
        await asyncio.sleep(0)
        return panel.beat.result

    assert asyncio.run(main()) == 2


def test_a_throttled_function_may_read_its_own_state_while_running() -> None:
    def peek() -> bool:
        return wrapped.pending

    wrapped = throttle(10, clock=FakeClock())(peek)
    worker = threading.Thread(target=wrapped, daemon=True)
    worker.start()
    worker.join(30)
    assert not worker.is_alive()


def test_async_throttle_on_a_new_loop_schedules_a_live_timer() -> None:
    scheduler, clock = FakeScheduler(), FakeClock()
    seen: list[int] = []

    @async_throttle(10, trailing=True, clock=clock, scheduler=scheduler)
    async def show(n: int) -> None:
        seen.append(n)

    async def first() -> None:
        show(1)
        show(2)
        await asyncio.sleep(0)

    async def second() -> None:
        show(3)
        assert len(scheduler.handles) == 2
        scheduler.handles[-1].fire()
        await asyncio.sleep(0)

    asyncio.run(first())
    asyncio.run(second())
    assert seen == [1, 3]


def test_async_throttle_ignores_a_stale_handle() -> None:
    scheduler, clock = FakeScheduler(), FakeClock()
    seen: list[int] = []

    @async_throttle(10, trailing=True, clock=clock, scheduler=scheduler)
    async def show(n: int) -> None:
        seen.append(n)

    async def main() -> None:
        show(1)
        show(2)
        show.cancel()
        show(3)
        scheduler.handles[0].action()  # cancelled, fires anyway
        await asyncio.sleep(0)

    asyncio.run(main())
    assert seen == [1]
    assert show.pending is True


def test_finished_runs_are_released_and_shutdown_is_not_a_failure() -> None:
    reported: list[Any] = []

    @async_debounce(60, leading=True)
    async def run(forever: bool) -> None:
        if forever:
            await asyncio.get_running_loop().create_future()

    async def main() -> int:
        asyncio.get_running_loop().set_exception_handler(lambda _, c: reported.append(c))
        run(False)
        for _ in range(3):
            await asyncio.sleep(0)
        held = len(run._runs._tasks)
        run.cancel()
        run(True)  # still running when the loop shuts down and cancels it
        await asyncio.sleep(0)
        return held

    assert asyncio.run(main()) == 0
    assert reported == []
