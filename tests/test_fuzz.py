"""Seeded fuzz: random calls and control operations on a virtual clock.

The sync and async wrappers must agree run for run, every run must be a real call made
no later than it runs, and the work per call must stay constant (a bounded number of
timers, never a growing queue).
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import pytest
from _virtual import VirtualTime

from throttlebounce import async_debounce, async_throttle, debounce, throttle

SEEDS = range(300)


def _plan(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    wait = rng.choice([0.0, 0.5, 1.0, 2.5])
    leading, trailing = rng.choice([(False, True), (True, False), (True, True)])
    events: list[tuple[float, str]] = []
    now = 0.0
    for _ in range(rng.randrange(1, 60)):
        now += rng.choice([0.0, 0.1, wait / 2, wait, rng.uniform(0, 4 * wait + 1)])
        events.append((now, rng.choice(["call"] * 8 + ["flush", "cancel", "reset"])))
    return {
        "kind": rng.choice(["debounce", "throttle"]),
        "wait": wait,
        "leading": leading,
        "trailing": trailing,
        "max_wait": rng.choice([None, wait, 2 * wait + 0.3, 5 * wait]),
        "events": events,
        "end": now + 10 * wait + 5,
    }


def _sync(plan: dict[str, Any]) -> tuple[list[tuple[float, int]], int]:
    time = VirtualTime()
    runs: list[tuple[float, int]] = []
    created = 0

    def factory(delay: float, action: Any) -> Any:
        nonlocal created
        created += 1
        return time.timer_factory(delay, action)

    def func(index: int) -> int:
        runs.append((time.now, index))
        return index

    w: Any
    if plan["kind"] == "debounce":
        options = {k: plan[k] for k in ("leading", "trailing", "max_wait")}
        w = debounce(plan["wait"], **options, timer_factory=factory)(func)
    else:
        w = throttle(
            plan["wait"], trailing=plan["trailing"], clock=time.clock, timer_factory=factory
        )(func)
    for index, (at, op) in enumerate(plan["events"]):
        time.advance(at)
        if op == "call":
            w(index)
        elif op != "reset" or plan["kind"] == "throttle":
            getattr(w, op)()
        assert time.queued() <= 2
    time.advance(plan["end"])
    return runs, created


def _async(plan: dict[str, Any]) -> list[tuple[float, int]]:
    time = VirtualTime()
    runs: list[tuple[float, int]] = []

    async def func(index: int) -> int:
        runs.append((time.now, index))
        return index

    async def drive() -> None:
        w: Any
        if plan["kind"] == "debounce":
            options = {k: plan[k] for k in ("leading", "trailing", "max_wait")}
            w = async_debounce(plan["wait"], **options, scheduler=time.scheduler)(func)
        else:
            w = async_throttle(
                plan["wait"], trailing=plan["trailing"], clock=time.clock, scheduler=time.scheduler
            )(func)
        for index, (at, op) in enumerate(plan["events"]):
            while time.next_due() <= at:
                time.advance(time.next_due())
                await asyncio.sleep(0)
            time.advance(at)
            if op == "call":
                w(index)
            elif op == "flush":
                await w.flush()
            elif op == "cancel" or plan["kind"] == "throttle":
                getattr(w, op)()
            await asyncio.sleep(0)
        while time.next_due() <= plan["end"]:
            time.advance(time.next_due())
            await asyncio.sleep(0)

    asyncio.run(drive())
    return runs


@pytest.mark.parametrize("seed", SEEDS)
def test_sync_and_async_agree_and_every_run_is_a_real_earlier_call(seed: int) -> None:
    plan = _plan(seed)
    if plan["max_wait"] is not None and plan["max_wait"] < plan["wait"]:
        plan["max_wait"] = plan["wait"]
    runs, created = _sync(plan)
    assert runs == _async(plan)
    calls = {i: at for i, (at, op) in enumerate(plan["events"]) if op == "call"}
    indices = [index for _, index in runs]
    assert indices == sorted(set(indices))
    assert all(index in calls and calls[index] <= at for at, index in runs)
    assert created <= 2 * len(plan["events"]) + len(runs)


def test_two_hundred_thousand_calls_keep_a_bounded_timer_queue() -> None:
    time = VirtualTime()
    seen: list[int] = []
    w = debounce(1.0, leading=True, max_wait=3.0, timer_factory=time.timer_factory)(seen.append)
    for index in range(200_000):
        time.advance(index * 0.01)
        w(index)
        assert time.queued() <= 4
    time.advance(1e9)
    assert len(seen) == 668
    assert seen[-1] == 199_999


def test_a_run_may_call_its_own_wrapper_without_deadlock() -> None:
    time = VirtualTime()
    seen: list[int] = []

    @debounce(1.0, leading=True, timer_factory=time.timer_factory)
    def again(n: int) -> None:
        seen.append(n)
        if n < 3:
            again(n + 1)

    again(0)
    time.advance(5)
    assert seen == [0, 1, 2, 3]
