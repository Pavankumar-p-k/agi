"""Minimal event primitives shared by backend plugin integrations."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


class PluginEventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def subscribe(self, event: str, handler: Callable[..., Any]) -> None:
        self._handlers[event].append(handler)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        for handler in tuple(self._handlers.get(event, ())):
            handler(*args, **kwargs)
