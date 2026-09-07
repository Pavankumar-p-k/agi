"""Tenant-aware EventBus."""
from __future__ import annotations
import asyncio
from collections import defaultdict
from typing import Callable, Any
from dataclasses import dataclass, field


@dataclass
class Event:
    event_type: str = ""
    data: Any = None
    tenant_id: str = "default"


class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable):
        self._listeners[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable):
        if handler in self._listeners[event_type]:
            self._listeners[event_type].remove(handler)

    async def publish(self, event_type: str, data: Any = None):
        for handler in self._listeners.get(event_type, []):
            try:
                res = handler(data)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass


global_event_bus = EventBus()
