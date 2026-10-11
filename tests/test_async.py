"""Behaviour tests for the async decorators, with a fake scheduler (no real waits)."""

from __future__ import annotations

import asyncio

import pytest
from _fakes import FakeClock, FakeScheduler, settle

from throttlebounce import async_debounce, async_throttle


def test_async_debounce_collapses_a_burst_into_one_trailing_run() -> None:
    async def scenario() -> None:
        sched = FakeScheduler()
        seen: list[int] = []

        @async_debounce(0.5, scheduler=sched)
        async def record(value: int) -> None:
            seen.append(value)

        record(1)
        record(2)
        record(3)
        await settle()
        assert seen == []
        sched.handles[-1].fire()
        await settle()
        assert seen == [3]
        assert record.result is None

    asyncio.run(scenario())


def test_async_debounce_leading_runs_the_first_call_at_once() -> None:
    async def scenario() -> None:
        sched = FakeScheduler()
        seen: list[int] = []

        @async_debounce(0.5, leading=True, trailing=False, scheduler=sched)
        async def record(value: int) -> None:
            seen.append(value)

        record(1)
        await settle()
        assert seen == [1]
        record(2)
        record(3)
        sched.handles[-1].fire()
        await settle()
        assert seen == [1]

    asyncio.run(scenario())


def test_async_debounce_flush_runs_the_pending_call_and_returns_it() -> None:
    async def scenario() -> None:
        sched = FakeScheduler()

        @async_debounce(0.5, scheduler=sched)
        async def double(value: int) -> int:
            return value * 2

        double(21)
        assert double.pending is True
        assert await double.flush() == 42
        assert double.pending is False
        assert double.result == 42

    asyncio.run(scenario())


def test_async_debounce_cancel_drops_the_pending_call() -> None:
    async def scenario() -> None:
        sched = FakeScheduler()
        seen: list[int] = []

        @async_debounce(0.5, scheduler=sched)
        async def record(value: int) -> None:
            seen.append(value)

        record(1)
        record.cancel()
        sched.handles[-1].fire()
        await settle()
        assert seen == []
        assert record.pending is False

    asyncio.run(scenario())


def test_async_throttle_runs_the_first_call_and_skips_within_the_interval() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        sched = FakeScheduler()
        seen: list[int] = []

        @async_throttle(1.0, clock=clock, scheduler=sched)
        async def record(value: int) -> None:
            seen.append(value)

        record(1)
        await settle()
        clock.advance(0.4)
        record(2)
        await settle()
        assert seen == [1]

    asyncio.run(scenario())


def test_async_throttle_trailing_runs_the_last_skipped_call() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        sched = FakeScheduler()
        seen: list[int] = []

        @async_throttle(1.0, trailing=True, clock=clock, scheduler=sched)
        async def record(value: int) -> None:
            seen.append(value)

        record(1)
        await settle()
        clock.advance(0.3)
        record(2)
        clock.advance(0.3)
        record(3)
        clock.advance(0.4)
        sched.handles[-1].fire()
        await settle()
        assert seen == [1, 3]

    asyncio.run(scenario())


def test_async_rejects_bad_arguments() -> None:
    with pytest.raises(ValueError):
        async_debounce(-1.0)
    with pytest.raises(ValueError):
        async_debounce(0.5, leading=False, trailing=False)
    with pytest.raises(ValueError):
        async_throttle(-1.0)
