"""The injectable time sources, and the checks every duration argument goes through."""

from __future__ import annotations

import numbers
import threading
from collections.abc import Callable
from typing import Protocol


class _Timer(Protocol):
    """The slice of threading.Timer the sync wrappers depend on."""

    def start(self) -> None: ...

    def cancel(self) -> None: ...


class _Handle(Protocol):
    """The slice of asyncio.TimerHandle the async wrappers depend on."""

    def cancel(self) -> None: ...


class Clock(Protocol):
    """Returns the current time in seconds; only differences between readings matter.

    The default is :func:`time.monotonic`. Inject your own in tests so nothing waits
    on real time:

    >>> from throttlebounce import throttle
    >>> now = [0.0]
    >>> runs = []
    >>> @throttle(1.0, clock=lambda: now[0])
    ... def tick() -> int:
    ...     runs.append(now[0])
    ...     return len(runs)
    >>> tick(), tick()
    (1, 1)
    >>> now[0] = 1.0
    >>> tick(), runs
    (2, [0.0, 1.0])
    """

    def __call__(self) -> float: ...


class TimerFactory(Protocol):
    """Builds a one-shot timer that runs ``action`` once, ``delay`` seconds after ``start()``.

    The timer must also offer ``cancel()``; :class:`threading.Timer` is the model and
    the default. Inject a factory that records the timers so a test fires them by hand:

    >>> from throttlebounce import debounce
    >>> class Manual:
    ...     def __init__(self, delay, action):
    ...         self.action, self.live = action, True
    ...     def start(self): pass
    ...     def cancel(self): self.live = False
    >>> timers = []
    >>> def factory(delay, action):
    ...     timers.append(Manual(delay, action))
    ...     return timers[-1]
    >>> @debounce(0.5, timer_factory=factory)
    ... def save(text: str) -> str:
    ...     return text
    >>> save("a"); save("ab")
    >>> [timer.action() for timer in timers if timer.live]
    [None]
    >>> save.result
    'ab'
    """

    def __call__(self, delay: float, action: Callable[[], None], /) -> _Timer: ...


class Scheduler(Protocol):
    """Schedules ``action`` to run ``delay`` seconds from now and returns a cancellable handle.

    The default is the running loop's :meth:`asyncio.loop.call_later`, so the async
    wrappers must be called while an event loop runs. Inject your own in tests:

    >>> import asyncio
    >>> from throttlebounce import async_debounce
    >>> actions = []
    >>> class Handle:
    ...     def cancel(self): pass
    >>> def scheduler(delay, action):
    ...     actions.append(action)
    ...     return Handle()
    >>> @async_debounce(0.5, scheduler=scheduler)
    ... async def push(value: int) -> int:
    ...     return value
    >>> async def main() -> int | None:
    ...     push(1)
    ...     actions[-1]()
    ...     await asyncio.sleep(0)
    ...     return push.result
    >>> asyncio.run(main())
    1
    """

    def __call__(self, delay: float, action: Callable[[], None], /) -> _Handle: ...


def _default_timer_factory(delay: float, action: Callable[[], None]) -> _Timer:
    # Daemon so a still-pending call never keeps the interpreter alive on exit.
    timer = threading.Timer(delay, action)
    timer.daemon = True
    return timer


def seconds(name: str, value: object) -> float:
    """Return ``value`` as float seconds, or raise for anything a timer cannot wait."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} must be a real number of seconds, not {type(value).__name__}")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        number = float("nan")
    if not 0 <= number <= threading.TIMEOUT_MAX:
        raise ValueError(f"{name} must be between 0 and {threading.TIMEOUT_MAX:g} seconds")
    return number


def edge_options(
    wait: object, leading: object, trailing: object, max_wait: object
) -> tuple[float, bool, bool, float | None]:
    """Validate the debounce options and return them normalised."""
    seconds_wait = seconds("wait", wait)
    limit = None if max_wait is None else seconds("max_wait", max_wait)
    if limit is not None and limit < seconds_wait:
        raise ValueError("max_wait must be at least wait")
    if not leading and not trailing:
        raise ValueError("leading and trailing cannot both be off: nothing would ever run")
    return seconds_wait, bool(leading), bool(trailing), limit
