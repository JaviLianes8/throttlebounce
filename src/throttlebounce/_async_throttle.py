"""Async throttle: run a coroutine at most once per interval, chosen edges."""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Awaitable, Callable
from typing import Generic, ParamSpec, TypeVar

from ._async_debounce import Scheduler, _default_scheduler, _Handle
from ._throttle import Clock

_P = ParamSpec("_P")
_R = TypeVar("_R")


class AsyncThrottled(Generic[_P, _R]):
    """A coroutine wrapper that throttles runs on an asyncio event loop.

    Must be called while an event loop is running. The first call runs at once
    (leading edge); with ``trailing`` on, the most recent call during a busy
    interval runs when the interval closes. The wrapped call returns None; read
    the latest value through ``result`` or await ``flush``.
    """

    def __init__(
        self,
        func: Callable[_P, Awaitable[_R]],
        interval: float,
        *,
        trailing: bool,
        clock: Clock,
        scheduler: Scheduler,
    ) -> None:
        self._func = func
        self._interval = interval
        self._trailing = trailing
        self._clock = clock
        self._schedule = scheduler
        self._last: float | None = None
        self._handle: _Handle | None = None
        self._pending: functools.partial[Awaitable[_R]] | None = None
        self._task: asyncio.Future[None] | None = None
        self._result: _R | None = None
        functools.update_wrapper(self, func)

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> None:
        call = functools.partial(self._func, *args, **kwargs)
        now = self._clock()
        if self._last is None or now - self._last >= self._interval:
            self._last = now
            self._pending = None
            if self._handle is not None:
                self._handle.cancel()
                self._handle = None
            self._spawn(call)
        elif self._trailing:
            self._pending = call
            if self._handle is None:
                remaining = self._interval - (now - self._last)
                self._handle = self._schedule(remaining, self._on_trailing)

    def _spawn(self, call: functools.partial[Awaitable[_R]]) -> None:
        self._task = asyncio.ensure_future(self._run(call()))

    async def _run(self, awaitable: Awaitable[_R]) -> None:
        self._result = await awaitable

    def _on_trailing(self) -> None:
        call = self._pending
        self._pending = None
        self._handle = None
        if call is not None:
            self._last = self._clock()
            self._spawn(call)

    def cancel(self) -> None:
        """Drop any pending trailing call so it will never run."""
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        self._pending = None

    async def flush(self) -> _R | None:
        """Run any pending trailing call now and return its result, else None."""
        call = self._pending
        self._pending = None
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        if call is None:
            return None
        self._last = self._clock()
        self._result = await call()
        return self._result

    def reset(self) -> None:
        """Forget the last run so the next call fires immediately."""
        self._last = None

    @property
    def pending(self) -> bool:
        """Whether a trailing call is waiting to run."""
        return self._pending is not None

    @property
    def result(self) -> _R | None:
        """The most recent result produced, or None before the first run."""
        return self._result


def async_throttle(
    interval: float,
    *,
    trailing: bool = False,
    clock: Clock = time.monotonic,
    scheduler: Scheduler = _default_scheduler,
) -> Callable[[Callable[_P, Awaitable[_R]]], AsyncThrottled[_P, _R]]:
    """Return a decorator that throttles a coroutine function.

    Mirrors :func:`throttlebounce.throttle` for asyncio: the first call runs at
    once, calls within ``interval`` are skipped, and ``trailing=True`` runs the
    most recent skipped call when the interval closes. The wrapped call returns
    None; await ``flush`` to force the pending run.
    """
    if interval < 0:
        raise ValueError("interval must be non-negative")

    def decorator(func: Callable[_P, Awaitable[_R]]) -> AsyncThrottled[_P, _R]:
        return AsyncThrottled(
            func,
            interval,
            trailing=trailing,
            clock=clock,
            scheduler=scheduler,
        )

    return decorator
