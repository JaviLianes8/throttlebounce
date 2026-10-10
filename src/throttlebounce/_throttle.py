"""Leading-edge throttle: run a function at most once per interval."""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from typing import Generic, ParamSpec, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")

Clock = Callable[[], float]
"""Returns a monotonically increasing time in seconds.

Inject a fake clock in tests so nothing waits on real time.
"""


class Throttled(Generic[_P, _R]):
    """A callable that runs ``func`` at most once per ``interval`` seconds."""

    def __init__(self, func: Callable[_P, _R], interval: float, clock: Clock) -> None:
        self._func = func
        self._interval = interval
        self._clock = clock
        self._lock = threading.Lock()
        self._last: float | None = None
        self._result: _R | None = None
        functools.update_wrapper(self, func)

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> _R | None:
        with self._lock:
            now = self._clock()
            if self._last is not None and now - self._last < self._interval:
                return self._result
            self._last = now
        result = self._func(*args, **kwargs)
        with self._lock:
            self._result = result
        return result

    def reset(self) -> None:
        """Forget the last run so the next call fires immediately."""
        with self._lock:
            self._last = None


def throttle(
    interval: float, *, clock: Clock = time.monotonic
) -> Callable[[Callable[_P, _R]], Throttled[_P, _R]]:
    """Return a decorator that throttles a function to once per ``interval`` seconds.

    The first call runs immediately; any call within ``interval`` of the last
    run is skipped and returns the last result (None before the first run).
    """
    if interval < 0:
        raise ValueError("interval must be non-negative")

    def decorator(func: Callable[_P, _R]) -> Throttled[_P, _R]:
        return Throttled(func, interval, clock)

    return decorator
