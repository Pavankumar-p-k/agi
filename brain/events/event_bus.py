from __future__ import annotations

import asyncio
import fnmatch
import inspect
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A typed event with metadata for the autonomous OS event bus.

    Every event carries:
      - type: dotted path string (e.g. "goal.created", "file.modified")
      - source: subsystem that emitted it
      - payload: the typed dataclass from event_types.py (stored as dict)
      - id: unique event ID
      - timestamp: ISO-8601
    """
    type: str
    source: str
    payload: dict
    id: str = ""
    timestamp: str = ""
    priority: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class Subscription:
    """A subscription handle. Can be cancelled."""
    pattern: str
    handler: Callable
    once: bool = False
    priority: int = 0
    _id: str = ""

    def __post_init__(self):
        if not self._id:
            self._id = str(uuid.uuid4())


class EventBus:
    """Typed, async-first event bus with pattern-based subscription.

    Patterns support:
      - Exact:      "goal.created"
      - Wildcard:   "goal.*"     (matches "goal.created", "goal.completed")
      - Multi:      "**"         (matches everything)

    Handlers are called asynchronously. Each event is dispatched to
    all matching subscribers in priority order.
    """

    def __init__(self):
        self._subscriptions: list[Subscription] = []
        self._lock = asyncio.Lock()
        self._stats: dict[str, int] = {}

    def subscribe(self, pattern: str, handler: Callable,
                  priority: int = 0, once: bool = False) -> Subscription:
        """Register a handler for events matching *pattern*.

        Returns a Subscription that can be cancelled with unsubscribe().
        """
        sub = Subscription(pattern=pattern, handler=handler,
                           priority=priority, once=once)
        self._subscriptions.append(sub)
        self._subscriptions.sort(key=lambda s: -s.priority)
        logger.debug("[EventBus] subscribed %s -> %s", pattern, handler.__name__)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        if sub in self._subscriptions:
            self._subscriptions.remove(sub)

    async def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers (async)."""
        self._stats[event.type] = self._stats.get(event.type, 0) + 1
        matched = []

        async with self._lock:
            for sub in self._subscriptions:
                if self._matches(sub.pattern, event.type):
                    matched.append(sub)

        for sub in matched:
            try:
                if inspect.iscoroutinefunction(sub.handler):
                    await sub.handler(event)
                else:
                    sub.handler(event)
            except Exception as e:
                logger.exception("[EventBus] handler %s failed for %s: %s",
                                 sub.handler.__name__, event.type, e)

            if sub.once:
                self._subscriptions.remove(sub)

    def _matches(self, pattern: str, event_type: str) -> bool:
        if pattern == "**":
            return True
        if "/" in pattern:
            return fnmatch.fnmatch(event_type, pattern)
        return fnmatch.fnmatch(event_type, pattern)

    def publish_sync(self, event: Event) -> None:
        """Synchronous publish — creates a task for async dispatch."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.publish(event))
            else:
                loop.run_until_complete(self.publish(event))
        except RuntimeError:
            asyncio.create_task(self.publish(event))

    def stats(self) -> dict:
        return dict(self._stats)

    def clear(self) -> None:
        self._subscriptions.clear()
        self._stats.clear()


# Global singleton
global_event_bus = EventBus()
