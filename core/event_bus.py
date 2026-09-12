"""Tenant-aware EventBus.

Central in-process event distribution.  Specialists and subsystems publish
lifecycle events (e.g. ``goal.completed``, ``action.verified``) and learning
components (pattern engine, habit tracker, experience recorder) subscribe
without any direct coupling between them.

Publishing never raises: a broken listener or consumer must not be able to
take down the producer.  Handler errors are logged, not silently swallowed.
"""
from __future__ import annotations
import asyncio
import logging
from collections import defaultdict
from typing import Callable, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Event:
    event_type: str = ""
    data: Any = None
    tenant_id: str = "default"


class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = defaultdict(list)
        self._failed_deliveries = 0

    def subscribe(self, event_type: str, handler: Callable):
        self._listeners[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable):
        if handler in self._listeners[event_type]:
            self._listeners[event_type].remove(handler)

    async def publish(self, event_type: str, data: Any = None):
        await self._dispatch(event_type, data, prefer_async=True)

    def publish_sync(self, event_type: str, data: Any = None):
        """Publish from synchronous (non-asyncio) contexts.

        - Sync handlers run inline, in subscription order.
        - Async handlers are scheduled on the running loop when one exists;
          otherwise executed with ``asyncio.run`` on a fresh loop.
        - Never raises: listener failures are logged and counted.
        """
        try:
            asyncio.get_running_loop()
            running_loop = True
        except RuntimeError:
            running_loop = False

        for handler in self._listeners.get(event_type, []):
            try:
                res = handler(data)
                if asyncio.iscoroutine(res):
                    if running_loop:
                        # We are inside a running loop's thread; schedule and move on.
                        asyncio.ensure_future(res)
                    else:
                        # No loop in this thread — own the coroutine's lifecycle.
                        asyncio.run(self._await_handler(res))
            except Exception as exc:
                self._failed_deliveries += 1
                logger.warning("[event_bus] handler error for %s: %s", event_type, exc)

    def failed_deliveries(self) -> int:
        return self._failed_deliveries

    async def _dispatch(self, event_type: str, data: Any, prefer_async: bool = True):
        for handler in self._listeners.get(event_type, []):
            try:
                res = handler(data)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as exc:
                self._failed_deliveries += 1
                logger.warning("[event_bus] handler error for %s: %s", event_type, exc)

    @staticmethod
    async def _await_handler(coro):
        await coro


global_event_bus = EventBus()
