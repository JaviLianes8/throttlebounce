"""The public promise: signatures, defaults, errors and wrapping, for every public name."""

from __future__ import annotations

import inspect
import math
from collections.abc import Callable
from fractions import Fraction
from typing import Any

import pytest
from _fakes import TimerSpy

import throttlebounce
from throttlebounce import async_debounce, async_throttle, debounce, throttle

DECORATORS: list[Callable[..., Any]] = [debounce, throttle, async_debounce, async_throttle]


def test_the_decorator_signatures_are_the_stable_ones() -> None:
    def shape(func: Callable[..., Any]) -> list[tuple[str, str, Any]]:
        return [
            (p.name, p.kind.name, p.default) for p in inspect.signature(func).parameters.values()
        ]

    edges = [("leading", "KEYWORD_ONLY", False), ("trailing", "KEYWORD_ONLY", True)]
    first = ("wait", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty)
    assert shape(debounce)[:4] == [first, *edges, ("max_wait", "KEYWORD_ONLY", None)]
    assert shape(async_debounce)[:4] == shape(debounce)[:4]
    assert [n for n, _, _ in shape(debounce)][4:] == ["timer_factory"]
    assert [n for n, _, _ in shape(async_debounce)][4:] == ["scheduler"]
    interval = ("interval", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty)
    assert shape(throttle)[:2] == [interval, ("trailing", "KEYWORD_ONLY", False)]
    assert [n for n, _, _ in shape(throttle)][2:] == ["clock", "timer_factory"]
    assert [n for n, _, _ in shape(async_throttle)][2:] == ["clock", "scheduler"]


def test_every_public_name_reports_the_package_and_has_a_runnable_example() -> None:
    for name in throttlebounce.__all__:
        value = getattr(throttlebounce, name)
        assert value.__module__ == "throttlebounce", name
        assert ">>> " in (value.__doc__ or ""), name


@pytest.mark.parametrize("factory", DECORATORS)
@pytest.mark.parametrize("bad", [-1, -0.001, math.nan, math.inf, -math.inf, 1e300, 10**400])
def test_a_duration_a_timer_cannot_wait_is_a_value_error(
    factory: Callable[..., Any], bad: object
) -> None:
    with pytest.raises(ValueError) as caught:
        factory(bad)
    assert len(str(caught.value)) < 80
    assert "seconds" in str(caught.value)


@pytest.mark.parametrize("factory", DECORATORS)
@pytest.mark.parametrize("bad", ["1", None, True, b"1", 1j, [1]])
def test_a_duration_that_is_not_a_real_number_is_a_type_error(
    factory: Callable[..., Any], bad: object
) -> None:
    with pytest.raises(TypeError, match="real number of seconds"):
        factory(bad)


@pytest.mark.parametrize("factory", DECORATORS)
@pytest.mark.parametrize("good", [0, 0.0, 1, 2.5, Fraction(1, 3)])
def test_any_finite_real_duration_is_accepted(factory: Callable[..., Any], good: object) -> None:
    factory(good)


@pytest.mark.parametrize("factory", [debounce, async_debounce])
def test_debounce_option_errors_are_raised_before_decorating(factory: Callable[..., Any]) -> None:
    with pytest.raises(ValueError, match="nothing would ever run"):
        factory(1.0, leading=False, trailing=False)
    with pytest.raises(ValueError, match="max_wait must be at least wait"):
        factory(1.0, max_wait=0.5)
    with pytest.raises(ValueError, match="max_wait"):
        factory(1.0, max_wait=-1)
    with pytest.raises(TypeError, match="max_wait"):
        factory(1.0, max_wait="2")
    factory(1.0, max_wait=1.0)


def test_the_classes_validate_like_the_decorators() -> None:
    with pytest.raises(ValueError):
        throttlebounce.Debounced(print, -1)
    with pytest.raises(ValueError):
        throttlebounce.Throttled(print, math.nan)
    with pytest.raises(TypeError):
        throttlebounce.AsyncDebounced(print, "1")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        throttlebounce.AsyncThrottled(print, -2)  # type: ignore[arg-type]


def test_the_wrapper_keeps_the_function_metadata() -> None:
    def greet(name: str) -> str:
        """Say hello."""
        return name

    for wrapped in (debounce(1)(greet), throttle(1)(greet)):
        assert vars(wrapped)["__name__"] == "greet"
        assert wrapped.__doc__ == "Say hello."
        assert vars(wrapped)["__wrapped__"] is greet


def test_attributes_of_the_wrapped_callable_never_replace_the_wrapper_state() -> None:
    class Job:
        def __init__(self) -> None:
            self._lock = "not a lock"
            self._edges = None
            self._func = None
            self._result = "stale"
            self.calls = 0

        def __call__(self) -> int:
            self.calls += 1
            return self.calls

    spy = TimerSpy()
    job = Job()
    deb = debounce(1, timer_factory=spy)(job)
    deb()
    assert deb.flush() == 1
    thr = throttle(1, clock=lambda: 0.0)(job)
    assert thr() == 2
    assert thr() == 2


def test_debounce_calls_return_none_and_throttle_calls_return_a_result() -> None:
    spy = TimerSpy()
    leading = debounce(1, leading=True, timer_factory=spy)(lambda: 5)
    assert leading() is None  # type: ignore[func-returns-value]
    assert leading.result == 5
    gate = throttle(1, clock=lambda: 0.0)(lambda: 6)
    assert gate() == 6


def test_attributes_of_the_function_never_hide_the_wrapper_methods() -> None:
    def job(value: int) -> int:
        return value

    for name in ("cancel", "flush", "reset", "pending", "_run", "_attr_name", "_edges"):
        setattr(job, name, "hidden")
    job.tag = "kept"  # type: ignore[attr-defined]
    spy = TimerSpy()
    deb = debounce(1, timer_factory=spy)(job)
    deb(1)
    assert deb.pending is True
    deb.cancel()
    assert deb.pending is False
    assert vars(deb)["tag"] == "kept"
    thr = throttle(1, clock=lambda: 0.0)(job)
    assert thr(5) == 5
    thr.reset()
    assert thr(6) == 6
