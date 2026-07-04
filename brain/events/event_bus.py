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
    pattern: str
    handler: Callable
    once: bool = False
    priority: int = 0
    _id: str = ""

    def __post_init__(self):
        if not self._id:
            self._id = str(uuid.uuid4())


class EventBus:
    """Canonical event bus — async-first, typed, pattern-based.

    Features:
      - Pattern subscription (exact, wildcard *, multi **)
      - Priority ordering
      - Async + sync publish
      - Streaming queue subscribers
      - In-memory event history ring buffer
      - Dispatch stats
    """

    def __init__(self):
        self._subscriptions: list[Subscription] = []
        self._lock = asyncio.Lock()
        self._stats: dict[str, int] = {}
        self._event_queues: list[asyncio.Queue[dict]] = []
        self._history: list[dict] = []
        self._max_history = 100

    # ── Pattern subscription ──────────────────────────────────

    def subscribe(self, pattern: str, handler: Callable,
                  priority: int = 0, once: bool = False) -> Subscription:
        sub = Subscription(pattern=pattern, handler=handler,
                           priority=priority, once=once)
        self._subscriptions.append(sub)
        self._subscriptions.sort(key=lambda s: -s.priority)
        logger.debug("[EventBus] subscribed %s -> %s", pattern, handler.__name__)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        if sub in self._subscriptions:
            self._subscriptions.remove(sub)

    # ── Streaming queue subscribers ───────────────────────────

    def subscribe_stream(self) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self._event_queues.append(queue)
        return queue

    def unsubscribe_stream(self, queue: asyncio.Queue[dict]) -> None:
        if queue in self._event_queues:
            self._event_queues.remove(queue)

    # ── Publish ───────────────────────────────────────────────

    async def publish(self, event: Event) -> None:
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

        stream_event = {
            "channel": event.type, "type": event.type,
            "source": event.source, "payload": event.payload,
            "id": event.id, "timestamp": event.timestamp,
        }
        for queue in self._event_queues:
            try:
                queue.put_nowait(stream_event)
            except asyncio.QueueFull:
                logger.debug("[EventBus] Dropped event for full stream queue: %s", event.type)

        self._history.append({
            "type": event.type, "source": event.source,
            "payload": event.payload, "timestamp": event.timestamp,
        })
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def _matches(self, pattern: str, event_type: str) -> bool:
        if pattern == "**":
            return True
        if "/" in pattern:
            return fnmatch.fnmatch(event_type, pattern)
        return fnmatch.fnmatch(event_type, pattern)

    def publish_sync(self, event: Event) -> None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.publish(event))
            else:
                loop.run_until_complete(self.publish(event))
        except RuntimeError:
            asyncio.create_task(self.publish(event))

    # ── Introspection ─────────────────────────────────────────

    def stats(self) -> dict:
        return dict(self._stats)

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()

    def clear(self) -> None:
        self._subscriptions.clear()
        self._stats.clear()
        self._event_queues.clear()
        self._history.clear()


# ── Global singleton ──────────────────────────────────────────

global_event_bus = EventBus()


# ── Backward-compat helpers (legacy core.event_bus API) ──────

_sub_map: dict[tuple[str, Callable], Subscription] = {}

def subscribe_event(pattern: str, handler: Callable) -> None:
    sub = global_event_bus.subscribe(pattern, handler)
    _sub_map[(pattern, handler)] = sub

def unsubscribe_event(pattern: str, handler: Callable) -> None:
    sub = _sub_map.pop((pattern, handler), None)
    if sub:
        global_event_bus.unsubscribe(sub)

def fire_event(event: str, data=None) -> None:
    payload = data if isinstance(data, dict) else {"data": data}
    ev = Event(type=event, source="system", payload=payload)
    global_event_bus.publish_sync(ev)

def get_task_scheduler():
    try:
        from core.scheduler import scheduler  # type: ignore
        return scheduler
    except ImportError:
        logger.warning("scheduler not available")
        return None


# ── Backward-compat PluginEventBus adapter ───────────────────

class PluginEventBus:
    """Adapter that routes plugin events through the canonical bus + plugin hooks."""

    _instance: PluginEventBus | None = None

    def __init__(self):
        self._bus = global_event_bus
        self._direct_handlers: dict[str, list[Callable]] = {}

    @classmethod
    def instance(cls) -> PluginEventBus:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._direct_handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        self._direct_handlers[event_type] = [
            h for h in self._direct_handlers.get(event_type, []) if h is not handler
        ]

    async def emit(self, event_type: str, **data: Any) -> list[Any]:
        results = []

        for handler in self._direct_handlers.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    r = await handler(event_type=event_type, **data)
                else:
                    r = handler(event_type=event_type, **data)
                results.append(r)
            except Exception as e:
                logger.exception("[PluginEventBus] Handler %s failed on %s: %s",
                                 getattr(handler, "__name__", "?"), event_type, e)

        ev = Event(type=event_type, source="plugin", payload=data)
        await self._bus.publish(ev)

        try:
            from core.plugins.base import plugin_registry  # type: ignore
            await plugin_registry.run_hook(event_type, **data)
        except Exception:
            logger.debug("PluginEventBus run_hook failed", exc_info=True)

        return results

    @property
    def history(self) -> list[dict]:
        return self._bus.history

    def clear_history(self) -> None:
        self._bus.clear_history()
