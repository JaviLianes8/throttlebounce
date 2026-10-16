"""The edge logic shared by the sync and async wrappers: no locks, no threads, no runs.

Each wrapper owns the lock (or the event loop) and runs what these state machines hand
back. Timers are created through ``new_timer`` and identified by a token, so a timer
that fires after it was replaced or cancelled is recognised as stale and ignored.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Generic, Protocol, TypeVar

_C = TypeVar("_C")


class _Cancellable(Protocol):
    def cancel(self) -> None: ...


NewTimer = Callable[[float, Callable[[], None]], _Cancellable]


class _Slot:
    """One live timer: its token is the identity a firing timer must match."""

    __slots__ = ("handle",)

    def __init__(self, new_timer: NewTimer, delay: float, fire: Callable[[_Slot], None]) -> None:
        self.handle = new_timer(delay, functools.partial(fire, self))


def _stop(slot: _Slot | None) -> None:
    if slot is not None:
        slot.handle.cancel()


class DebounceEdges(Generic[_C]):
    """A burst lasts while calls arrive less than ``wait`` apart.

    The quiet timer runs ``wait`` after the latest call and ends the burst. The deadline
    timer runs ``max_wait`` after the burst started or after the last run inside it.
    """

    def __init__(
        self,
        wait: float,
        *,
        leading: bool,
        trailing: bool,
        max_wait: float | None,
        new_timer: NewTimer,
        fire: Callable[[_Slot], None],
    ) -> None:
        self._wait = wait
        self._leading = leading
        self._trailing = trailing
        self._max_wait = max_wait
        self._new_timer = new_timer
        self._fire = fire
        self._quiet: _Slot | None = None
        self._deadline: _Slot | None = None
        self._pending: _C | None = None
        # The deadline passed with nothing to run: the next call opens a new burst.
        self._expired = False

    @property
    def pending(self) -> bool:
        return self._pending is not None

    def call(self, call: _C) -> _C | None:
        run: _C | None = None
        if self._quiet is None or self._expired:
            self._expired = False
            self._restart_deadline()
            if self._leading:
                run = call
                self._pending = None
            else:
                self._pending = call
        elif self._trailing:
            self._pending = call
        _stop(self._quiet)
        self._quiet = _Slot(self._new_timer, self._wait, self._fire)
        return run

    def _restart_deadline(self) -> None:
        _stop(self._deadline)
        self._deadline = None
        if self._max_wait is not None:
            self._deadline = _Slot(self._new_timer, self._max_wait, self._fire)

    def expire(self, slot: _Slot) -> _C | None:
        run = self._pending
        if slot is self._quiet:
            self._quiet = None
            _stop(self._deadline)
            self._deadline = None
            self._expired = False
        elif slot is self._deadline:
            self._deadline = None
            if run is None:
                self._expired = True
            else:
                self._restart_deadline()
        else:
            return None
        self._pending = None
        return run

    def cancel(self) -> None:
        self._pending = None
        self.end()

    def take(self) -> _C | None:
        run = self._pending
        self._pending = None
        self.end()
        return run

    def end(self) -> None:
        _stop(self._quiet)
        _stop(self._deadline)
        self._quiet = self._deadline = None
        self._expired = False


class ThrottleEdges(Generic[_C]):
    """Runs at most once per ``interval``, measured from the start of the last run."""

    def __init__(
        self,
        interval: float,
        *,
        trailing: bool,
        new_timer: NewTimer,
        fire: Callable[[_Slot], None],
    ) -> None:
        self._interval = interval
        self._trailing = trailing
        self._new_timer = new_timer
        self._fire = fire
        self._last: float | None = None
        self._timer: _Slot | None = None
        self._pending: _C | None = None

    @property
    def pending(self) -> bool:
        return self._pending is not None

    def call(self, call: _C, now: float) -> _C | None:
        elapsed = None if self._last is None else now - self._last
        # A clock that went backwards is treated as a closed window, never a stuck one.
        if elapsed is None or elapsed >= self._interval or elapsed < 0:
            self._last = now
            self.cancel()
            return call
        if self._trailing:
            self._pending = call
            if self._timer is None:
                self._timer = _Slot(self._new_timer, self._interval - elapsed, self._fire)
        return None

    def expire(self, slot: _Slot, now: float) -> _C | None:
        if slot is not self._timer:
            return None
        self._timer = None
        return self._started(now)

    def take(self, now: float) -> _C | None:
        _stop(self._timer)
        self._timer = None
        return self._started(now)

    def _started(self, now: float) -> _C | None:
        run = self._pending
        self._pending = None
        if run is not None:
            self._last = now
        return run

    def cancel(self) -> None:
        _stop(self._timer)
        self._timer = None
        self._pending = None

    def reset(self) -> None:
        self._last = None
