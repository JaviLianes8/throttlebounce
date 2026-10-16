"""Per-instance binding, so a decorated method keeps separate timing for each object."""

from __future__ import annotations

from collections.abc import Callable
from types import MethodType
from typing import Any


class Bindable:
    """Mixin for the wrappers: reading one through an instance gives that instance's own.

    The bound wrapper is cached in the instance ``__dict__`` under the attribute name,
    the way :func:`functools.cached_property` caches, so two objects never share a
    pending call and an object keeps its state across reads.
    """

    _func: Callable[..., Any]
    _attr_name: str | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr_name = name

    def _bind_to(self, obj: object) -> Any:
        name = self._attr_name or getattr(self._func, "__name__", None)
        try:
            namespace = vars(obj)
        except TypeError:
            namespace = None
        if namespace is None or not isinstance(name, str):
            raise TypeError(
                f"cannot bind to {type(obj).__name__} instances: "
                "a decorated method needs an instance __dict__ to keep its state"
            )
        bound = self._rebuild(MethodType(self._func, obj))
        return namespace.setdefault(name, bound)

    def _rebuild(self, func: Callable[..., Any]) -> Any:
        raise NotImplementedError
