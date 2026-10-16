"""Debounce: collapse a burst of calls into one run, on the edges you choose."""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from typing import Any, Generic, ParamSpec, TypeVar, overload

from ._bind import Bindable
from ._edges import DebounceEdges, _Slot
from ._types import TimerFactory, _default_timer_factory, _Timer, edge_options

_P = ParamSpec("_P")
_R = TypeVar("_R")


class Debounced(Bindable, Generic[_P, _R]):
    """A callable that delays ``func`` around a burst of calls; built by :func:`debounce`.

    Calling it returns None: runs happen on a timer thread, or inside the call for the
    leading edge. Thread-safe; ``func`` always runs outside the internal lock.

    >>> from throttlebounce import debounce
    >>> @debounce(60.0)
    ... def save(text: str) -> int:
    ...     return len(text)
    >>> save("h"); save("hello")
    >>> save.pending
    True
    >>> save.flush()
    5
    >>> save.pending, save.result
    (False, 5)
    """

    def __init__(
        self,
        func: Callable[_P, _R],
        wait: float,
        *,
        leading: bool = False,
        trailing: bool = True,
        max_wait: float | None = None,
        timer_factory: TimerFactory = _default_timer_factory,
    ) -> None:
        wait, leading, trailing, max_wait = edge_options(wait, leading, trailing, max_wait)
        self._func = func
        self._settings = (wait, leading, trailing, max_wait, timer_factory)
        self._factory = timer_factory
        self._lock = threading.Lock()
        self._starting: list[_Timer] = []
        self._edges: DebounceEdges[functools.partial[_R]] = DebounceEdges(
            wait,
            leading=leading,
            trailing=trailing,
            max_wait=max_wait,
            new_timer=self._new_timer,
            fire=self._fire,
        )
        self._result: _R | None = None
        functools.update_wrapper(self, func)

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> None:
        call = functools.partial(self._func, *args, **kwargs)
        with self._lock:
            run = self._edges.call(call)
            starting = self._take_starting()
        for timer in starting:
            timer.start()
        if run is not None:
            self._run(run)

    def _new_timer(self, delay: float, action: Callable[[], None]) -> _Timer:
        timer = self._factory(delay, action)
        self._starting.append(timer)
        return timer

    def _take_starting(self) -> list[_Timer]:
        # Timers start outside the lock, so a factory that fires at once cannot deadlock.
        starting, self._starting = self._starting, []
        return starting

    def _fire(self, slot: _Slot) -> None:
        with self._lock:
            run = self._edges.expire(slot)
            starting = self._take_starting()
        for timer in starting:
            timer.start()
        if run is not None:
            self._run(run)

    def _run(self, call: functools.partial[_R]) -> _R:
        result = call()
        with self._lock:
            self._result = result
        return result

    def cancel(self) -> None:
        """Drop the pending call, if any, and end the burst."""
        with self._lock:
            self._edges.cancel()

    def flush(self) -> _R | None:
        """Run the pending call now and return its result; None when nothing is pending.

        The burst ends either way, so the next call opens a new one.
        """
        with self._lock:
            run = self._edges.take()
        return None if run is None else self._run(run)

    @property
    def pending(self) -> bool:
        """Whether a call is waiting for the trailing edge or the ``max_wait`` deadline."""
        with self._lock:
            return self._edges.pending

    @property
    def result(self) -> _R | None:
        """What the most recent run returned, or None before the first run."""
        with self._lock:
            return self._result

    def _rebuild(self, func: Callable[..., Any]) -> Debounced[..., _R]:
        wait, leading, trailing, max_wait, factory = self._settings
        return Debounced(
            func, wait, leading=leading, trailing=trailing, max_wait=max_wait, timer_factory=factory
        )

    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> Debounced[_P, _R]: ...
    @overload
    def __get__(self, obj: object, objtype: type | None = None) -> Debounced[..., _R]: ...
    def __get__(self, obj: object, objtype: type | None = None) -> Debounced[Any, _R]:
        return self if obj is None else self._bind_to(obj)


def debounce(
    wait: float,
    *,
    leading: bool = False,
    trailing: bool = True,
    max_wait: float | None = None,
    timer_factory: TimerFactory = _default_timer_factory,
) -> Callable[[Callable[_P, _R]], Debounced[_P, _R]]:
    """Return a decorator that debounces a function.

    A burst is a run of calls less than ``wait`` seconds apart. By default the function
    runs once, ``wait`` seconds after the last call of the burst, with that call's
    arguments (trailing edge). ``leading=True`` runs it on the first call of the burst;
    with both edges on, the trailing run happens only if another call came after the
    leading one. ``max_wait`` (at least ``wait``) caps how long a call can be held: during
    an unbroken burst the latest call runs ``max_wait`` after the burst began, then again
    ``max_wait`` after each such run.

    Raises TypeError if a duration is not a real number, and ValueError if it is negative,
    NaN, infinite, beyond :data:`threading.TIMEOUT_MAX`, if ``max_wait < wait``, or if
    both edges are off.

    >>> @debounce(60.0, leading=True)
    ... def ping(n: int) -> int:
    ...     return n
    >>> ping(1); ping.result
    1
    >>> ping(2); ping(3); ping.flush()
    3
    """
    edge_options(wait, leading, trailing, max_wait)

    def decorator(func: Callable[_P, _R]) -> Debounced[_P, _R]:
        return Debounced(
            func,
            wait,
            leading=leading,
            trailing=trailing,
            max_wait=max_wait,
            timer_factory=timer_factory,
        )

    return decorator
