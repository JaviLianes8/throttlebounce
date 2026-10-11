"""Async debounce: collapse a burst of coroutine calls, on the chosen edges."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import Generic, ParamSpec, Protocol, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")


class _Handle(Protocol):
    """The slice of asyncio.TimerHandle the async timers depend on."""

    def cancel(self) -> None: ...


Scheduler = Callable[[float, Callable[[], None]], _Handle]
"""Schedules an action to run after a delay on the running event loop.

Inject a fake scheduler in tests so nothing waits on real time.
"""


def _default_scheduler(delay: float, action: Callable[[], None]) -> _Handle:
    return asyncio.get_running_loop().call_later(delay, action)


class AsyncDebounced(Generic[_P, _R]):
    """A coroutine wrapper that debounces runs on an asyncio event loop.

    Must be called while an event loop is running. The wrapper schedules the real
    coroutine with the loop; calling it returns None (runs happen later). Use the
    async ``flush`` to run the pending call now, ``cancel`` to drop it, and the
    ``pending`` and ``result`` properties to inspect state.
    """

    def __init__(
        self,
        func: Callable[_P, Awaitable[_R]],
        wait: float,
        *,
        leading: bool,
        trailing: bool,
        max_wait: float | None,
        scheduler: Scheduler,
    ) -> None:
        self._func = func
        self._wait = wait
        self._leading = leading
        self._trailing = trailing
        self._max_wait = max_wait
        self._schedule = scheduler
        self._handle: _Handle | None = None
        self._max_handle: _Handle | None = None
        self._pending: functools.partial[Awaitable[_R]] | None = None
        self._task: asyncio.Future[None] | None = None
        self._result: _R | None = None
        self._burst = False
        functools.update_wrapper(self, func)

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> None:
        call = functools.partial(self._func, *args, **kwargs)
        leading_edge = not self._burst
        self._burst = True
        if leading_edge and self._leading:
            self._pending = None
            self._spawn(call)
        else:
            self._pending = call
        if self._handle is not None:
            self._handle.cancel()
        self._handle = self._schedule(self._wait, self._on_trailing)
        if self._max_wait is not None and self._max_handle is None:
            self._max_handle = self._schedule(self._max_wait, self._on_max)

    def _spawn(self, call: functools.partial[Awaitable[_R]]) -> None:
        self._task = asyncio.ensure_future(self._run(call()))

    async def _run(self, awaitable: Awaitable[_R]) -> None:
        self._result = await awaitable

    def _clear_timers(self) -> None:
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        if self._max_handle is not None:
            self._max_handle.cancel()
            self._max_handle = None
        self._burst = False

    def _on_trailing(self) -> None:
        self._handle = None
        if self._max_handle is not None:
            self._max_handle.cancel()
            self._max_handle = None
        self._burst = False
        call = self._pending if self._trailing else None
        self._pending = None
        if call is not None:
            self._spawn(call)

    def _on_max(self) -> None:
        self._max_handle = None
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        self._burst = False
        call = self._pending
        self._pending = None
        if call is not None:
            self._spawn(call)

    def cancel(self) -> None:
        """Drop any pending call so it will never run."""
        self._pending = None
        self._clear_timers()

    async def flush(self) -> _R | None:
        """Run any pending call now and return its result, else None."""
        call = self._pending
        self._pending = None
        self._clear_timers()
        if call is None:
            return None
        self._result = await call()
        return self._result

    @property
    def pending(self) -> bool:
        """Whether a call is waiting to run."""
        return self._pending is not None

    @property
    def result(self) -> _R | None:
        """The most recent result produced, or None before the first run."""
        return self._result


def async_debounce(
    wait: float,
    *,
    leading: bool = False,
    trailing: bool = True,
    max_wait: float | None = None,
    scheduler: Scheduler = _default_scheduler,
) -> Callable[[Callable[_P, Awaitable[_R]]], AsyncDebounced[_P, _R]]:
    """Return a decorator that debounces a coroutine function.

    Mirrors :func:`throttlebounce.debounce` for asyncio: rapid calls collapse
    into as few runs as the edges allow, scheduled on the running loop with no
    threads. ``leading``, ``trailing`` and ``max_wait`` behave as on the sync
    side. The wrapped call returns None; await ``flush`` to force a run.
    """
    if wait < 0:
        raise ValueError("wait must be non-negative")
    if max_wait is not None and max_wait < 0:
        raise ValueError("max_wait must be non-negative")
    if not leading and not trailing:
        raise ValueError("async_debounce must fire on at least one edge")

    def decorator(func: Callable[_P, Awaitable[_R]]) -> AsyncDebounced[_P, _R]:
        return AsyncDebounced(
            func,
            wait,
            leading=leading,
            trailing=trailing,
            max_wait=max_wait,
            scheduler=scheduler,
        )

    return decorator
