"""Decorated methods: each instance gets its own wrapper, cached on the instance."""

from __future__ import annotations

import asyncio

import pytest
from _fakes import FakeClock, FakeScheduler, TimerSpy

from throttlebounce import (
    AsyncDebounced,
    AsyncThrottled,
    Debounced,
    Throttled,
    async_debounce,
    async_throttle,
    debounce,
    throttle,
)

SPY = TimerSpy()
CLOCK = FakeClock()
SCHEDULER = FakeScheduler()


class Editor:
    def __init__(self, name: str) -> None:
        self.name = name
        self.saved: list[str] = []

    @debounce(1, timer_factory=SPY)
    def save(self, text: str) -> str:
        self.saved.append(text)
        return f"{self.name}:{text}"

    @throttle(1, clock=CLOCK)
    def ping(self) -> str:
        return self.name

    @async_debounce(1, scheduler=SCHEDULER)
    async def push(self, value: int) -> int:
        return value

    @async_throttle(1, clock=CLOCK, scheduler=SCHEDULER)
    async def beat(self, value: int) -> int:
        return value


def test_reading_through_the_class_gives_the_shared_wrapper() -> None:
    assert isinstance(Editor.save, Debounced)
    assert isinstance(Editor.ping, Throttled)
    assert isinstance(Editor.push, AsyncDebounced)
    assert isinstance(Editor.beat, AsyncThrottled)


def test_each_instance_keeps_its_own_pending_call() -> None:
    first, second = Editor("a"), Editor("b")
    first.save("one")
    second.save("two")
    assert first.save is first.save
    assert first.save is not second.save
    assert first.save.flush() == "a:one"
    assert second.save.flush() == "b:two"
    assert (first.saved, second.saved) == (["one"], ["two"])
    assert vars(first)["save"] is first.save


def test_each_instance_has_its_own_throttle_window() -> None:
    first, second = Editor("a"), Editor("b")
    assert first.ping() == "a"
    assert second.ping() == "b"
    assert first.ping() == "a"


def test_async_methods_bind_per_instance() -> None:
    async def main() -> tuple[int | None, int | None]:
        first, second = Editor("a"), Editor("b")
        first.push(1)
        second.push(2)
        first.beat(3)
        await asyncio.sleep(0)
        return await second.push.flush(), first.beat.result

    assert asyncio.run(main()) == (2, 3)


def test_a_class_without_an_instance_dict_is_refused_clearly() -> None:
    class Slotted:
        __slots__ = ()

        @debounce(1, timer_factory=SPY)
        def save(self) -> None:
            pass

    with pytest.raises(TypeError, match="instance __dict__"):
        Slotted().save()


def test_a_wrapper_assigned_after_class_creation_binds_by_its_function_name() -> None:
    class Late:
        pass

    def tick(self: Late) -> int:
        return 7

    Late.tick = throttle(1, clock=CLOCK)(tick)  # type: ignore[attr-defined]
    late = Late()
    assert late.tick() == 7  # type: ignore[attr-defined]
    assert "tick" in vars(late)
