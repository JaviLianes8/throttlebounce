"""Small, typed, zero-dependency sync debounce and throttle decorators."""

from __future__ import annotations

from ._debounce import Debounced, TimerFactory, debounce
from ._throttle import Clock, Throttled, throttle

__version__ = "0.1.0"

__all__ = [
    "Clock",
    "Debounced",
    "Throttled",
    "TimerFactory",
    "debounce",
    "throttle",
]
