"""The async promise beyond the shared edge logic: tasks, the loop, and failures."""

from __future__ import annotations

import asyncio
import gc
import weakref

import pytest
from _fakes import FakeClock, FakeScheduler

from throttlebounce import async_debounce, async_throttle


def test_calls_outside_a_running_loop_raise_and_change_nothing() -> None:
    clock, scheduler = FakeClock(), FakeScheduler()

    @async_debounce(1, scheduler=scheduler)
    async def push() -> None:
        pass

    @async_throttle(1, clock=clock, scheduler=scheduler)
    async def beat() -> int:
        return 1

    for wrapper in (push, beat):
        with pytest.raises(RuntimeError):
            wrapper()
    assert (push.pending, scheduler.handles) == (False, [])

    async def main() -> int | None:
        beat()  # the failed call above opened no window
        await asyncio.sleep(0)
        return beat.result

    assert asyncio.run(main()) == 1


def test_a_failing_timed_run_goes_to_the_loop_exception_handler() -> None:
    async def main() -> list[BaseException]:
        caught: list[BaseException] = []
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda _, context: caught.append(context["exception"]))
        scheduler = FakeScheduler()

        @async_debounce(1, scheduler=scheduler)
        async def fail() -> None:
            raise KeyError("boom")

        fail()
        scheduler.handles[-1].fire()
        for _ in range(3):
            await asyncio.sleep(0)
        return caught

    caught = asyncio.run(main())
    assert [type(error) for error in caught] == [KeyError]


def test_a_spawned_run_survives_garbage_collection_until_it_finishes() -> None:
    # The event loop holds tasks only weakly: a run waiting on a future nothing else
    # references is collected halfway unless the wrapper holds its task.
    async def main() -> list[str]:
        waiting: list[weakref.ref[asyncio.Future[None]]] = []
        seen: list[str] = []

        @async_throttle(60)
        async def slow() -> None:
            future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            waiting.append(weakref.ref(future))
            await future
            seen.append("done")

        slow()
        await asyncio.sleep(0)
        gc.collect()
        future = waiting[0]()
        assert future is not None
        future.set_result(None)
        del future
        for _ in range(5):
            await asyncio.sleep(0)
        return seen

    assert asyncio.run(main()) == ["done"]


def test_result_is_the_latest_finished_run_and_a_failure_leaves_it() -> None:
    async def main() -> tuple[int | None, int | None]:
        scheduler = FakeScheduler()

        @async_debounce(1, scheduler=scheduler)
        async def maybe(value: int) -> int:
            if value < 0:
                raise ValueError("negative")
            return value

        maybe(3)
        assert await maybe.flush() == 3
        maybe(-1)
        with pytest.raises(ValueError):
            await maybe.flush()
        return maybe.result, await maybe.flush()

    assert asyncio.run(main()) == (3, None)


def test_cancel_drops_the_pending_call_but_not_a_run_already_started() -> None:
    async def main() -> list[int]:
        scheduler, clock = FakeScheduler(), FakeClock()
        seen: list[int] = []

        @async_throttle(10, trailing=True, clock=clock, scheduler=scheduler)
        async def show(value: int) -> None:
            await asyncio.sleep(0)
            seen.append(value)

        show(1)
        show(2)
        show.cancel()
        assert show.pending is False
        scheduler.handles[0].action()  # a stale handle firing anyway
        for _ in range(5):
            await asyncio.sleep(0)
        return seen

    assert asyncio.run(main()) == [1]


def test_async_flush_and_reset_mirror_the_sync_throttle() -> None:
    async def main() -> tuple[int | None, bool, int | None]:
        scheduler, clock = FakeScheduler(), FakeClock()

        @async_throttle(10, trailing=True, clock=clock, scheduler=scheduler)
        async def show(value: int) -> int:
            return value

        show(1)
        show(2)
        flushed = await show.flush()
        show(3)  # inside the window the flush opened
        waiting = show.pending
        show.reset()
        show(4)
        await asyncio.sleep(0)
        return flushed, waiting, show.result

    assert asyncio.run(main()) == (2, True, 4)
