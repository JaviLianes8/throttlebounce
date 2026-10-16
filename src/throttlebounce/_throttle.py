"""Throttle: run a function at most once per interval, on the edges you choose."""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from typing import Any, Generic, ParamSpec, TypeVar, overload

from ._bind import Bindable
from ._edges import ThrottleEdges, _Slot
from ._types import Clock, TimerFactory, _default_timer_factory, _Timer, seconds

_P = ParamSpec("_P")
_R = TypeVar("_R")


class Throttled(Bindable, Generic[_P, _R]):
    """A callable that runs ``func`` at most once per ``interval``; built by :func:`throttle`.

    A call that runs returns the new result; a skipped call returns the latest result
    (None before the first run). Thread-safe; ``func`` runs outside the internal lock.

    >>> from throttlebounce import throttle
    >>> @throttle(60.0, trailing=True)
    ... def show(n: int) -> int:
    ...     return n
    >>> show(1), show(2), show(3)
    (1, 1, 1)
    >>> show.pending, show.flush(), show.result
    (True, 3, 3)
    """

    def __init__(
        self,
        func: Callable[_P, _R],
        interval: float,
        *,
        trailing: bool = False,
        clock: Clock = time.monotonic,
        timer_factory: TimerFactory = _default_timer_factory,
    ) -> None:
        interval = seconds("interval", interval)
        # Copy the metadata first, so attributes of func can never replace our state.
        functools.update_wrapper(self, func)
        self._func = func
        self._settings = (interval, bool(trailing), clock, timer_factory)
        self._clock = clock
        self._factory = timer_factory
        self._lock = threading.Lock()
        self._starting: list[_Timer] = []
        self._edges: ThrottleEdges[functools.partial[_R]] = ThrottleEdges(
            interval, trailing=bool(trailing), new_timer=self._new_timer, fire=self._fire
        )
        self._result: _R | None = None

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> _R | None:
        call = functools.partial(self._func, *args, **kwargs)
        with self._lock:
            run = self._edges.call(call, self._clock())
            starting, self._starting = self._starting, []
            result = self._result
        for timer in starting:
            timer.start()
        return result if run is None else self._run(run)

    def _new_timer(self, delay: float, action: Callable[[], None]) -> _Timer:
        timer = self._factory(delay, action)
        self._starting.append(timer)
        return timer

    def _fire(self, slot: _Slot) -> None:
        with self._lock:
            run = self._edges.expire(slot, self._clock())
        if run is not None:
            self._run(run)

    def _run(self, call: functools.partial[_R]) -> _R:
        result = call()
        with self._lock:
            self._result = result
        return result

    def cancel(self) -> None:
        """Drop the pending trailing call, if any; the current window stays."""
        with self._lock:
            self._edges.cancel()

    def flush(self) -> _R | None:
        """Run the pending trailing call now and return its result; None if none.

        The run counts as the start of a new window.
        """
        with self._lock:
            run = self._edges.take(self._clock())
        return None if run is None else self._run(run)

    def reset(self) -> None:
        """Forget the last run, so the next call runs at once."""
        with self._lock:
            self._edges.reset()

    @property
    def pending(self) -> bool:
        """Whether a trailing call is waiting for the window to close."""
        with self._lock:
            return self._edges.pending

    @property
    def result(self) -> _R | None:
        """What the most recent run returned, or None before the first run."""
        with self._lock:
            return self._result

    def _rebuild(self, func: Callable[..., Any]) -> Throttled[..., _R]:
        interval, trailing, clock, factory = self._settings
        return Throttled(func, interval, trailing=trailing, clock=clock, timer_factory=factory)

    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> Throttled[_P, _R]: ...
    @overload
    def __get__(self, obj: object, objtype: type | None = None) -> Throttled[..., _R]: ...
    def __get__(self, obj: object, objtype: type | None = None) -> Throttled[Any, _R]:
        return self if obj is None else self._bind_to(obj)


def throttle(
    interval: float,
    *,
    trailing: bool = False,
    clock: Clock = time.monotonic,
    timer_factory: TimerFactory = _default_timer_factory,
) -> Callable[[Callable[_P, _R]], Throttled[_P, _R]]:
    """Return a decorator that throttles a function to one run per ``interval`` seconds.

    The first call runs at once (leading edge) and opens a window of ``interval``
    seconds; calls inside the window are skipped and return the latest result. With
    ``trailing=True`` the most recent skipped call runs when the window closes, which
    opens the next window, so the final value of a busy stretch is never lost. A clock
    reading earlier than the last run counts as a closed window.

    Raises TypeError if ``interval`` is not a real number, and ValueError if it is
    negative, NaN, infinite or beyond :data:`threading.TIMEOUT_MAX`.

    >>> @throttle(60.0)
    ... def hello(name: str) -> str:
    ...     return f"hello {name}"
    >>> hello("ana"), hello("bob")
    ('hello ana', 'hello ana')
    """
    seconds("interval", interval)

    def decorator(func: Callable[_P, _R]) -> Throttled[_P, _R]:
        return Throttled(
            func, interval, trailing=trailing, clock=clock, timer_factory=timer_factory
        )

    return decorator
