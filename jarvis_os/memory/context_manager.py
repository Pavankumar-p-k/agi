from __future__ import annotations

from collections import deque
from typing import Any


class ContextManager:
    def __init__(self, limit: int) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=limit)

    def remember(self, item: dict[str, Any]) -> None:
        self._events.append(item)

    def recent(self, *, kinds: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        items = list(self._events)
        if kinds:
            allowed = set(kinds)
            items = [item for item in items if item.get("kind") in allowed]
        if limit is not None:
            items = items[-limit:]
        return items
