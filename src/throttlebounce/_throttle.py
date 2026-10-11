"""Throttle: run a function at most once per interval, on the edges you choose."""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from typing import Generic, ParamSpec, TypeVar

from ._debounce import TimerFactory, _default_timer_factory, _Timer

_P = ParamSpec("_P")
_R = TypeVar("_R")

Clock = Callable[[], float]
"""Returns a monotonically increasing time in seconds.

Inject a fake clock in tests so nothing waits on real time.
"""


class Throttled(Generic[_P, _R]):
    """A callable that runs ``func`` at most once per ``interval`` seconds.

    The first call runs immediately (leading edge). With ``trailing`` on, the
    most recent call that arrived during a busy interval also runs when the
    interval closes, so the final value is never dropped.
    """

    def __init__(
        self,
        func: Callable[_P, _R],
        interval: float,
        *,
        trailing: bool,
        clock: Clock,
        timer_factory: TimerFactory,
    ) -> None:
        self._func = func
        self._interval = interval
        self._trailing = trailing
        self._clock = clock
        self._new_timer = timer_factory
        self._lock = threading.Lock()
        self._last: float | None = None
        self._timer: _Timer | None = None
        self._pending: functools.partial[_R] | None = None
        self._result: _R | None = None
        functools.update_wrapper(self, func)

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> _R | None:
        call = functools.partial(self._func, *args, **kwargs)
        start_timer: _Timer | None = None
        run_now: functools.partial[_R] | None = None
        with self._lock:
            now = self._clock()
            if self._last is None or now - self._last >= self._interval:
                self._last = now
                run_now = call
                self._pending = None
                if self._timer is not None:
                    self._timer.cancel()
                    self._timer = None
            elif self._trailing:
                self._pending = call
                if self._timer is None:
                    remaining = self._interval - (now - self._last)
                    self._timer = self._new_timer(remaining, self._on_trailing)
                    start_timer = self._timer
        if start_timer is not None:
            start_timer.start()
        if run_now is not None:
            return self._run(run_now)
        with self._lock:
            return self._result

    def _on_trailing(self) -> None:
        with self._lock:
            call = self._pending
            self._pending = None
            self._timer = None
            if call is not None:
                self._last = self._clock()
        if call is not None:
            self._run(call)

    def _run(self, call: functools.partial[_R]) -> _R:
        result = call()
        with self._lock:
            self._result = result
        return result

    def cancel(self) -> None:
        """Drop any pending trailing call so it will never run."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending = None

    def flush(self) -> _R | None:
        """Run any pending trailing call now and return its result, else None."""
        with self._lock:
            call = self._pending
            self._pending = None
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if call is not None:
                self._last = self._clock()
        if call is None:
            return None
        return self._run(call)

    def reset(self) -> None:
        """Forget the last run so the next call fires immediately."""
        with self._lock:
            self._last = None

    @property
    def pending(self) -> bool:
        """Whether a trailing call is waiting to run."""
        with self._lock:
            return self._pending is not None

    @property
    def result(self) -> _R | None:
        """The most recent result produced, or None before the first run."""
        with self._lock:
            return self._result


def throttle(
    interval: float,
    *,
    trailing: bool = False,
    clock: Clock = time.monotonic,
    timer_factory: TimerFactory = _default_timer_factory,
) -> Callable[[Callable[_P, _R]], Throttled[_P, _R]]:
    """Return a decorator that throttles a function to once per ``interval``.

    The first call runs immediately; any call within ``interval`` of the last run
    is skipped and returns the last result (None before the first run). With
    ``trailing=True`` the most recent skipped call is scheduled to run when the
    interval closes, so the final value in a busy window is not lost; ``flush``
    runs it now, ``cancel`` drops it, ``pending`` reports it, and ``result``
    reads the last value produced. ``reset`` clears the window.
    """
    if interval < 0:
        raise ValueError("interval must be non-negative")

    def decorator(func: Callable[_P, _R]) -> Throttled[_P, _R]:
        return Throttled(
            func,
            interval,
            trailing=trailing,
            clock=clock,
            timer_factory=timer_factory,
        )

    return decorator
