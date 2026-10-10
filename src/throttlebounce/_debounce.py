"""Trailing-edge debounce: run a function only after its calls go quiet."""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from typing import Generic, ParamSpec, Protocol, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")


class _Timer(Protocol):
    """The slice of threading.Timer the debouncer depends on."""

    def start(self) -> None: ...

    def cancel(self) -> None: ...


TimerFactory = Callable[[float, Callable[[], None]], _Timer]
"""Builds a one-shot timer that runs an action after a delay in seconds.

Inject a fake factory in tests so nothing waits on real time.
"""


def _default_timer_factory(delay: float, action: Callable[[], None]) -> _Timer:
    # Daemon so a still-pending call never keeps the interpreter alive on exit.
    timer = threading.Timer(delay, action)
    timer.daemon = True
    return timer


class Debounced(Generic[_P, _R]):
    """A callable that delays ``func`` until ``wait`` seconds after the last call."""

    def __init__(self, func: Callable[_P, _R], wait: float, timer_factory: TimerFactory) -> None:
        self._func = func
        self._wait = wait
        self._new_timer = timer_factory
        self._lock = threading.Lock()
        self._timer: _Timer | None = None
        self._pending: functools.partial[_R] | None = None
        self._result: _R | None = None
        functools.update_wrapper(self, func)

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> None:
        call = functools.partial(self._func, *args, **kwargs)
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._pending = call
            timer = self._new_timer(self._wait, self._fire)
            self._timer = timer
        timer.start()

    def _fire(self) -> None:
        with self._lock:
            call = self._pending
            self._pending = None
            self._timer = None
        if call is not None:
            self._result = call()

    def cancel(self) -> None:
        """Drop any pending call so it will never run."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending = None

    def flush(self) -> _R | None:
        """Run any pending call right now and return its result, else None."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            call = self._pending
            self._pending = None
        if call is None:
            return None
        self._result = call()
        return self._result

    @property
    def pending(self) -> bool:
        """Whether a call is waiting to run."""
        with self._lock:
            return self._pending is not None


def debounce(
    wait: float, *, timer_factory: TimerFactory = _default_timer_factory
) -> Callable[[Callable[_P, _R]], Debounced[_P, _R]]:
    """Return a decorator that debounces a function by ``wait`` seconds.

    Rapid calls collapse into one: the wrapped function runs ``wait`` seconds
    after the final call, with that call's arguments. The debounced callable
    returns None (the real run happens later); use ``flush`` to force it now,
    ``cancel`` to drop it, and ``pending`` to check for a waiting call.
    """
    if wait < 0:
        raise ValueError("wait must be non-negative")

    def decorator(func: Callable[_P, _R]) -> Debounced[_P, _R]:
        return Debounced(func, wait, timer_factory)

    return decorator
