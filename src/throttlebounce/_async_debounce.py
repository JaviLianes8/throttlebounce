"""Async debounce: collapse a burst of coroutine calls, on the chosen edges."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import Any, Concatenate, Generic, ParamSpec, TypeVar, overload

from ._bind import Bindable, wrap
from ._edges import DebounceEdges, _Slot
from ._types import Scheduler, _Handle, edge_options

_P = ParamSpec("_P")
_R = TypeVar("_R")
_S = TypeVar("_S")
_Q = ParamSpec("_Q")


def _default_scheduler(delay: float, action: Callable[[], None]) -> _Handle:
    return asyncio.get_running_loop().call_later(delay, action)


class Runs(Generic[_R]):
    """Spawns runs as tasks, holds them until done, and keeps the latest result."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Future[None]] = set()
        self.result: _R | None = None

    def spawn(self, call: Callable[[], Awaitable[_R]]) -> None:
        # The loop keeps only weak references to tasks; holding them here stops a
        # running call from being collected halfway.
        task = asyncio.ensure_future(self._run(call))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, call: Callable[[], Awaitable[_R]]) -> None:
        try:
            await self.now(call)
        except Exception as error:
            # Nobody awaits a timed run: report its failure the way the loop reports
            # any unhandled task error, instead of a warning when the task is collected.
            asyncio.get_running_loop().call_exception_handler(
                {"message": "throttlebounce run failed", "exception": error}
            )

    async def now(self, call: Callable[[], Awaitable[_R]]) -> _R:
        result = await call()
        self.result = result
        return result


class AsyncDebounced(Bindable, Generic[_P, _R]):
    """A coroutine wrapper that debounces on the running event loop; see :func:`async_debounce`.

    Calling it returns None and must happen while a loop runs: each run is a task on
    that loop. Not thread-safe; use it from the loop's thread.

    >>> import asyncio
    >>> from throttlebounce import async_debounce
    >>> @async_debounce(60.0)
    ... async def push(value: int) -> int:
    ...     return value
    >>> async def main() -> tuple[bool, int | None]:
    ...     push(1); push(2)
    ...     return push.pending, await push.flush()
    >>> asyncio.run(main())
    (True, 2)
    """

    def __init__(
        self,
        func: Callable[_P, Awaitable[_R]],
        wait: float,
        *,
        leading: bool = False,
        trailing: bool = True,
        max_wait: float | None = None,
        scheduler: Scheduler = _default_scheduler,
    ) -> None:
        wait, leading, trailing, max_wait = edge_options(wait, leading, trailing, max_wait)
        wrap(self, func)
        self._func = func
        self._settings = (wait, leading, trailing, max_wait, scheduler)
        self._runs: Runs[_R] = Runs()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._edges: DebounceEdges[functools.partial[Awaitable[_R]]] = DebounceEdges(
            wait,
            leading=leading,
            trailing=trailing,
            max_wait=max_wait,
            new_timer=scheduler,
            fire=self._fire,
        )

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> None:
        loop = asyncio.get_running_loop()  # no running loop: RuntimeError, state untouched
        if loop is not self._loop:
            # Timers of a previous loop died with it: what they held is dropped.
            self._edges.cancel()
            self._loop = loop
        run = self._edges.call(functools.partial(self._func, *args, **kwargs))
        if run is not None:
            self._runs.spawn(run)

    def _fire(self, slot: _Slot) -> None:
        run = self._edges.expire(slot)
        if run is not None:
            self._runs.spawn(run)

    def cancel(self) -> None:
        """Drop the pending call, if any, and end the burst. Runs already started go on."""
        self._edges.cancel()

    async def flush(self) -> _R | None:
        """Run the pending call now, await it and return its result; None if none."""
        run = self._edges.take()
        return None if run is None else await self._runs.now(run)

    @property
    def pending(self) -> bool:
        """Whether a call is waiting for the trailing edge or the ``max_wait`` deadline."""
        return self._edges.pending

    @property
    def result(self) -> _R | None:
        """What the most recently finished run returned, or None before any finished."""
        return self._runs.result

    def _rebuild(self, func: Callable[..., Any]) -> AsyncDebounced[..., _R]:
        wait, leading, trailing, max_wait, scheduler = self._settings
        return AsyncDebounced(
            func, wait, leading=leading, trailing=trailing, max_wait=max_wait, scheduler=scheduler
        )

    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> AsyncDebounced[_P, _R]: ...
    @overload
    def __get__(
        self: AsyncDebounced[Concatenate[_S, _Q], _R], obj: _S, objtype: type | None = None
    ) -> AsyncDebounced[_Q, _R]: ...
    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        return self if obj is None else self._bind_to(obj)


def async_debounce(
    wait: float,
    *,
    leading: bool = False,
    trailing: bool = True,
    max_wait: float | None = None,
    scheduler: Scheduler = _default_scheduler,
) -> Callable[[Callable[_P, Awaitable[_R]]], AsyncDebounced[_P, _R]]:
    """Return a decorator that debounces a coroutine function.

    The same edges, ``max_wait`` and errors as :func:`throttlebounce.debounce`, scheduled
    on the running event loop with no threads.

    >>> import asyncio
    >>> @async_debounce(60.0, leading=True)
    ... async def ping(n: int) -> int:
    ...     return n
    >>> async def main() -> int | None:
    ...     ping(1)
    ...     await asyncio.sleep(0)
    ...     return ping.result
    >>> asyncio.run(main())
    1
    """
    edge_options(wait, leading, trailing, max_wait)

    def decorator(func: Callable[_P, Awaitable[_R]]) -> AsyncDebounced[_P, _R]:
        return AsyncDebounced(
            func, wait, leading=leading, trailing=trailing, max_wait=max_wait, scheduler=scheduler
        )

    return decorator
