"""Tenant-aware EventBus with a legacy convenience API.

Two publish styles coexist:

1. Tenant-style: ``await bus.publish(Event(...))`` — every matching
   subscription handler receives the Event object (used by the
   tenant-isolation and observation tests).
2. Legacy-style: ``bus.publish("event.type", {"k": v})`` (or
   ``publish_sync``) — matching handlers receive the *payload* directly,
   so specialist/learning handlers stay plain ``lambda data: ...``.

Broken handlers are counted by ``failed_deliveries()`` and never break
other listeners.
"""
from __future__ import annotations

import asyncio
import fnmatch
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Event:
    type: str
    source: str = ""
    payload: Any = None
    resource_scope: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @property
    def tenant_id(self) -> str:
        return (self.resource_scope or {}).get("tenant_id", "default")

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "source": self.source,
            "payload": self.payload,
            "resource_scope": dict(self.resource_scope),
        }

    def __getitem__(self, key: str):
        """Dict-style access to payload fields (payload must be a dict)."""
        if isinstance(self.payload, dict):
            return self.payload[key]
        raise KeyError(key)


@dataclass
class Subscription:
    pattern: str
    handler: Callable
    tenant_id: Optional[str] = None

    def matches(self, event: Event) -> bool:
        if not fnmatch.fnmatch(event.type, self.pattern):
            return False
        if self.tenant_id is not None:
            return event.tenant_id == self.tenant_id
        return True


# Bounded per-subscriber stream queues (websocket/SSE fan-out).
STREAM_QUEUE_MAXSIZE = 100


class EventBus:
    def __init__(self) -> None:
        self._subscriptions: list[Subscription] = []
        self._failed = 0
        self._stream_queues: list[asyncio.Queue] = []
        self._stream_drops = 0
        self._websocket_connections = 0

    # ── streaming subscribers ────────────────────────────────────────
    def subscribe_stream(self, maxsize: int | None = None) -> asyncio.Queue:
        """Register a bounded queue that receives every published event."""
        queue: asyncio.Queue = asyncio.Queue(
            maxsize=maxsize if maxsize is not None else STREAM_QUEUE_MAXSIZE)
        self._stream_queues.append(queue)
        return queue

    def unsubscribe_stream(self, queue: asyncio.Queue) -> None:
        try:
            self._stream_queues.remove(queue)
        except ValueError:
            pass

    def add_websocket(self) -> None:
        self._websocket_connections += 1

    def remove_websocket(self) -> None:
        self._websocket_connections = max(0, self._websocket_connections - 1)

    def _fanout_stream(self, message: dict) -> None:
        for queue in list(self._stream_queues):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                self._stream_drops += 1

    def health(self) -> dict:
        """Operational counters for the observability surface."""
        return {
            "stream_queues": len(self._stream_queues),
            "stream_queue_depth": sum(q.qsize() for q in self._stream_queues),
            "websocket_connections": self._websocket_connections,
            "queue_drops": self._stream_drops,
            "failed_deliveries": self._failed,
            "subscriptions": len(self._subscriptions),
        }

    # ── registration ─────────────────────────────────────────────────
    def subscribe(self, pattern_or_type: str, handler: Callable,
                  tenant_id: Optional[str] = None) -> Subscription:
        sub = Subscription(pattern=pattern_or_type, handler=handler,
                           tenant_id=tenant_id)
        self._subscriptions.append(sub)
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        try:
            self._subscriptions.remove(subscription)
        except ValueError:
            pass

    # ── publishing (async) ───────────────────────────────────────────
    async def publish(self, type_or_event, payload: Any = None) -> None:
        if isinstance(type_or_event, Event):
            event = type_or_event
            self._fanout_stream(event.to_dict())
            for sub in list(self._subscriptions):
                if not sub.matches(event):
                    continue
                try:
                    result = sub.handler(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:  # noqa: BLE001 — handlers must not break the bus
                    self._failed += 1
            return

        # Legacy: (event_type, payload) — handlers receive the payload.
        event_type = str(type_or_event)
        self._fanout_stream({"event": event_type, "payload": payload})
        for sub in list(self._subscriptions):
            if not fnmatch.fnmatch(event_type, sub.pattern):
                continue
            try:
                result = sub.handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001
                self._failed += 1

    # ── publishing (sync) ────────────────────────────────────────────
    def publish_sync(self, type_or_event, payload: Any = None) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if isinstance(type_or_event, Event):
            if loop is not None:
                loop.create_task(self.publish(type_or_event))
            else:
                asyncio.run(self.publish(type_or_event))
            return

        # Legacy: run handlers inline so sync callers see immediate effects.
        event_type = str(type_or_event)
        for sub in list(self._subscriptions):
            if not fnmatch.fnmatch(event_type, sub.pattern):
                continue
            try:
                result = sub.handler(payload)
                if asyncio.iscoroutine(result):
                    if loop is not None:
                        loop.create_task(result)
                    else:
                        asyncio.run(result)
            except Exception:  # noqa: BLE001
                self._failed += 1

    # ── diagnostics ──────────────────────────────────────────────────
    def failed_deliveries(self) -> int:
        return self._failed


# Module-level default bus.
global_event_bus = EventBus()


__all__ = ["Event", "EventBus", "Subscription", "global_event_bus"]
