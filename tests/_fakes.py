"""Shared test doubles: fake timers, clocks and schedulers (no real waits)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable


class FakeClock:
    """A clock the test advances by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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


class FakeHandle:
    """A scheduled async action that fires only when the test tells it to."""

    def __init__(self, delay: float, action: Callable[[], None]) -> None:
        self.delay = delay
        self.action = action
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.action()


class FakeScheduler:
    """Records every action it schedules so a test can fire the live one."""

    def __init__(self) -> None:
        self.handles: list[FakeHandle] = []

    def __call__(self, delay: float, action: Callable[[], None]) -> FakeHandle:
        handle = FakeHandle(delay, action)
        self.handles.append(handle)
        return handle


async def settle() -> None:
    """Let any just-spawned task run to completion."""
    await asyncio.sleep(0)
    await asyncio.sleep(0)
