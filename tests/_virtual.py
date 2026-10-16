"""A virtual clock with timers, and the scenario runner the oracle tests share.

Timers due at or before a call's time fire before that call, in due order and then
creation order, which is the order tests/oracle/run.cjs gives the JavaScript libraries.
"""

from __future__ import annotations

import asyncio
import heapq
from collections.abc import Callable
from typing import Any

from throttlebounce import async_debounce, async_throttle, debounce, throttle


class VirtualTimer:
    def __init__(self, time: VirtualTime, delay: float, action: Callable[[], None]) -> None:
        self.time, self.delay, self.action = time, delay, action
        self.live = False

    def start(self) -> None:
        self.live = True
        self.time.push(self)

    def cancel(self) -> None:
        self.live = False


class VirtualTime:
    """Hand-driven time: ``clock``, ``timer_factory`` and ``scheduler`` share one queue."""

    def __init__(self) -> None:
        self.now = 0.0
        self._queue: list[tuple[float, int, VirtualTimer]] = []
        self._sequence = 0

    def clock(self) -> float:
        return self.now

    def timer_factory(self, delay: float, action: Callable[[], None]) -> VirtualTimer:
        return VirtualTimer(self, delay, action)

    def scheduler(self, delay: float, action: Callable[[], None]) -> VirtualTimer:
        timer = VirtualTimer(self, delay, action)
        timer.start()
        return timer

    def push(self, timer: VirtualTimer) -> None:
        heapq.heappush(self._queue, (self.now + timer.delay, self._sequence, timer))
        self._sequence += 1

    def next_due(self) -> float:
        return self._queue[0][0] if self._queue else float("inf")

    def advance(self, to: float) -> None:
        while self._queue and self._queue[0][0] <= to:
            due, _, timer = heapq.heappop(self._queue)
            if timer.live:
                timer.live = False
                self.now = due
                timer.action()
        self.now = max(self.now, to)


def run_sync(s: dict[str, Any]) -> dict[str, Any]:
    """Run one scenario through the sync decorators."""
    time = VirtualTime()
    runs: list[list[float]] = []

    def func(index: int) -> int:
        runs.append([time.now, index])
        return index

    wrapped: Callable[[int], Any]
    if s["kind"] == "debounce":
        wrapped = debounce(
            s["wait"],
            leading=s["leading"],
            trailing=s["trailing"],
            max_wait=s["max_wait"],
            timer_factory=time.timer_factory,
        )(func)
    else:
        wrapped = throttle(
            s["wait"], trailing=s["trailing"], clock=time.clock, timer_factory=time.timer_factory
        )(func)
    returns = []
    for index, at in enumerate(s["calls"]):
        time.advance(at)
        returns.append(wrapped(index))
    time.advance(s["end"])
    return {"runs": runs, "returns": returns}


def run_async(s: dict[str, Any]) -> dict[str, Any]:
    """Run one scenario through the async decorators, letting each spawned run finish."""
    time = VirtualTime()
    runs: list[list[float]] = []

    async def func(index: int) -> int:
        runs.append([time.now, index])
        return index

    async def drive() -> None:
        wrapped: Callable[[int], None]
        if s["kind"] == "debounce":
            wrapped = async_debounce(
                s["wait"],
                leading=s["leading"],
                trailing=s["trailing"],
                max_wait=s["max_wait"],
                scheduler=time.scheduler,
            )(func)
        else:
            wrapped = async_throttle(
                s["wait"], trailing=s["trailing"], clock=time.clock, scheduler=time.scheduler
            )(func)
        for index, at in enumerate(s["calls"]):
            await _advance(time, at)
            wrapped(index)
            await _settle()
        await _advance(time, s["end"])

    asyncio.run(drive())
    return {"runs": runs, "returns": None}


async def _settle() -> None:
    for _ in range(3):
        await asyncio.sleep(0)


async def _advance(time: VirtualTime, to: float) -> None:
    # Fire one instant at a time so each spawned run starts at its own virtual time.
    while time.next_due() <= to:
        time.advance(time.next_due())
        await _settle()
    time.advance(to)
    await _settle()
