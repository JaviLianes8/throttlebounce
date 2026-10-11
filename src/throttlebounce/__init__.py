"""Small, typed, zero-dependency debounce and throttle, sync and async."""

from __future__ import annotations

from ._async_debounce import AsyncDebounced, Scheduler, async_debounce
from ._async_throttle import AsyncThrottled, async_throttle
from ._debounce import Debounced, TimerFactory, debounce
from ._throttle import Clock, Throttled, throttle

__version__ = "0.2.0"

__all__ = [
    "AsyncDebounced",
    "AsyncThrottled",
    "Clock",
    "Debounced",
    "Scheduler",
    "Throttled",
    "TimerFactory",
    "async_debounce",
    "async_throttle",
    "debounce",
    "throttle",
]
