"""Debounce: collapse a burst of calls into one run, on the edges you choose."""

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
    """A callable that delays ``func`` around a burst of calls.

    With the defaults it runs once, ``wait`` seconds after the last call
    (trailing edge). ``leading`` adds a run on the first call of a burst, and
    ``max_wait`` guarantees a run at least that often during a sustained burst.
    """

    def __init__(
        self,
        func: Callable[_P, _R],
        wait: float,
        *,
        leading: bool,
        trailing: bool,
        max_wait: float | None,
        timer_factory: TimerFactory,
    ) -> None:
        self._func = func
        self._wait = wait
        self._leading = leading
        self._trailing = trailing
        self._max_wait = max_wait
        self._new_timer = timer_factory
        self._lock = threading.Lock()
        self._timer: _Timer | None = None
        self._max_timer: _Timer | None = None
        self._pending: functools.partial[_R] | None = None
        self._result: _R | None = None
        self._burst = False
        functools.update_wrapper(self, func)

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> None:
        call = functools.partial(self._func, *args, **kwargs)
        run_now: functools.partial[_R] | None = None
        with self._lock:
            leading_edge = not self._burst
            self._burst = True
            if leading_edge and self._leading:
                run_now = call
                self._pending = None
            else:
                self._pending = call
            if self._timer is not None:
                self._timer.cancel()
            self._timer = self._new_timer(self._wait, self._on_trailing)
            trailing_timer = self._timer
            max_timer: _Timer | None = None
            if self._max_wait is not None and self._max_timer is None:
                self._max_timer = self._new_timer(self._max_wait, self._on_max)
                max_timer = self._max_timer
        trailing_timer.start()
        if max_timer is not None:
            max_timer.start()
        if run_now is not None:
            self._result = run_now()

    def _end_burst_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._max_timer is not None:
            self._max_timer.cancel()
            self._max_timer = None
        self._burst = False

    def _on_trailing(self) -> None:
        with self._lock:
            call = self._pending if self._trailing else None
            self._pending = None
            self._timer = None
            if self._max_timer is not None:
                self._max_timer.cancel()
                self._max_timer = None
            self._burst = False
        if call is not None:
            self._result = call()

    def _on_max(self) -> None:
        with self._lock:
            call = self._pending
            self._pending = None
            self._max_timer = None
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._burst = False
        if call is not None:
            self._result = call()

    def cancel(self) -> None:
        """Drop any pending call so it will never run."""
        with self._lock:
            self._pending = None
            self._end_burst_locked()

    def flush(self) -> _R | None:
        """Run any pending call right now and return its result, else None."""
        with self._lock:
            call = self._pending
            self._pending = None
            self._end_burst_locked()
        if call is None:
            return None
        self._result = call()
        return self._result

    @property
    def pending(self) -> bool:
        """Whether a call is waiting to run."""
        with self._lock:
            return self._pending is not None

    @property
    def result(self) -> _R | None:
        """The most recent result produced, or None before the first run."""
        with self._lock:
            return self._result


def debounce(
    wait: float,
    *,
    leading: bool = False,
    trailing: bool = True,
    max_wait: float | None = None,
    timer_factory: TimerFactory = _default_timer_factory,
) -> Callable[[Callable[_P, _R]], Debounced[_P, _R]]:
    """Return a decorator that debounces a function.

    Rapid calls collapse into as few runs as the edges allow. By default the
    wrapped function runs once, ``wait`` seconds after the final call, with that
    call's arguments (trailing edge). Set ``leading=True`` to also run on the
    first call of a burst; with both edges on, the trailing run happens only when
    more than one call arrived. ``max_wait`` forces a run at least that often
    during an unbroken burst, so a continuous stream is never starved.

    The debounced callable returns None (deferred runs happen on a timer); use
    ``flush`` to force the pending call now, ``cancel`` to drop it, ``pending``
    to check for a waiting call, and ``result`` to read the last value produced.
    """
    if wait < 0:
        raise ValueError("wait must be non-negative")
    if max_wait is not None and max_wait < 0:
        raise ValueError("max_wait must be non-negative")
    if not leading and not trailing:
        raise ValueError("debounce must fire on at least one edge")

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
