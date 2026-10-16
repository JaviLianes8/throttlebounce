"""Async throttle: run a coroutine at most once per interval, on the chosen edges."""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any, Generic, ParamSpec, TypeVar, overload

from ._async_debounce import Runs, _default_scheduler
from ._bind import Bindable
from ._edges import ThrottleEdges, _Slot
from ._types import Clock, Scheduler, seconds

_P = ParamSpec("_P")
_R = TypeVar("_R")


class AsyncThrottled(Bindable, Generic[_P, _R]):
    """A coroutine wrapper that throttles on the running event loop; see :func:`async_throttle`.

    Calling it returns None and must happen while a loop runs: each run is a task on
    that loop. Not thread-safe; use it from the loop's thread.

    >>> import asyncio
    >>> from throttlebounce import async_throttle
    >>> @async_throttle(60.0, trailing=True)
    ... async def show(n: int) -> int:
    ...     return n
    >>> async def main() -> tuple[int | None, int | None]:
    ...     show(1); show(2); show(3)
    ...     await asyncio.sleep(0)
    ...     return show.result, await show.flush()
    >>> asyncio.run(main())
    (1, 3)
    """

    def __init__(
        self,
        func: Callable[_P, Awaitable[_R]],
        interval: float,
        *,
        trailing: bool = False,
        clock: Clock = time.monotonic,
        scheduler: Scheduler = _default_scheduler,
    ) -> None:
        interval = seconds("interval", interval)
        self._func = func
        self._settings = (interval, bool(trailing), clock, scheduler)
        self._clock = clock
        self._runs: Runs[_R] = Runs()
        self._edges: ThrottleEdges[functools.partial[Awaitable[_R]]] = ThrottleEdges(
            interval, trailing=bool(trailing), new_timer=scheduler, fire=self._fire
        )
        functools.update_wrapper(self, func)

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> None:
        call = functools.partial(self._func, *args, **kwargs)
        run = self._edges.call(call, self._clock())
        if run is not None:
            self._runs.spawn(run)

    def _fire(self, slot: _Slot) -> None:
        run = self._edges.expire(slot, self._clock())
        if run is not None:
            self._runs.spawn(run)

    def cancel(self) -> None:
        """Drop the pending trailing call, if any; the current window stays."""
        self._edges.cancel()

    async def flush(self) -> _R | None:
        """Run the pending trailing call now, await it and return its result; None if none.

        The run counts as the start of a new window.
        """
        run = self._edges.take(self._clock())
        return None if run is None else await self._runs.now(run)

    def reset(self) -> None:
        """Forget the last run, so the next call runs at once."""
        self._edges.reset()

    @property
    def pending(self) -> bool:
        """Whether a trailing call is waiting for the window to close."""
        return self._edges.pending

    @property
    def result(self) -> _R | None:
        """What the most recently finished run returned, or None before any finished."""
        return self._runs.result

    def _rebuild(self, func: Callable[..., Any]) -> AsyncThrottled[..., _R]:
        interval, trailing, clock, scheduler = self._settings
        return AsyncThrottled(func, interval, trailing=trailing, clock=clock, scheduler=scheduler)

    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> AsyncThrottled[_P, _R]: ...
    @overload
    def __get__(self, obj: object, objtype: type | None = None) -> AsyncThrottled[..., _R]: ...
    def __get__(self, obj: object, objtype: type | None = None) -> AsyncThrottled[Any, _R]:
        return self if obj is None else self._bind_to(obj)


def async_throttle(
    interval: float,
    *,
    trailing: bool = False,
    clock: Clock = time.monotonic,
    scheduler: Scheduler = _default_scheduler,
) -> Callable[[Callable[_P, Awaitable[_R]]], AsyncThrottled[_P, _R]]:
    """Return a decorator that throttles a coroutine function.

    The same windows, ``trailing`` edge and errors as :func:`throttlebounce.throttle`,
    scheduled on the running event loop with no threads.

    >>> import asyncio
    >>> @async_throttle(60.0)
    ... async def beat(n: int) -> int:
    ...     return n
    >>> async def main() -> int | None:
    ...     beat(1); beat(2)
    ...     await asyncio.sleep(0)
    ...     return beat.result
    >>> asyncio.run(main())
    1
    """
    seconds("interval", interval)

    def decorator(func: Callable[_P, Awaitable[_R]]) -> AsyncThrottled[_P, _R]:
        return AsyncThrottled(func, interval, trailing=trailing, clock=clock, scheduler=scheduler)

    return decorator
