"""Small, typed, zero-dependency debounce and throttle, sync and async."""

from __future__ import annotations

from ._async_debounce import AsyncDebounced, async_debounce
from ._async_throttle import AsyncThrottled, async_throttle
from ._debounce import Debounced, debounce
from ._throttle import Throttled, throttle
from ._types import Clock, Scheduler, TimerFactory

__version__ = "1.0.0"

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
