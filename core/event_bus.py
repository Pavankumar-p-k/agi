# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import asyncio
import inspect
import logging
import threading
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    """Unified Event Bus supporting sync, async, and streaming subscribers."""
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._event_queues: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()

    def subscribe(self, channel: str, callback: Callable) -> None:
        with self._lock:
            self._subscribers[channel].append(callback)

    def unsubscribe(self, channel: str, callback: Callable) -> None:
        with self._lock:
            try:
                self._subscribers[channel].remove(callback)
            except ValueError:
                pass

    def publish(self, channel: str, payload: dict[str, Any]) -> None:
        """Publish an event to all subscribers."""
        # Wrap payload with channel info for streaming
        event = {"channel": channel, **payload}
        
        with self._lock:
            handlers = list(self._subscribers.get(channel, []))
            wildcard = list(self._subscribers.get("*", []))
        
        all_handlers = handlers + wildcard
        
        # Notify handlers
        for handler in all_handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    async def _safe_handler():
                        try:
                            await handler(channel, payload)
                        except Exception as err:
                            logger.error("EventBus handler error for %s: %s", channel, err)
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.ensure_future(_safe_handler())
                        else:
                            loop.run_until_complete(_safe_handler())
                    except RuntimeError:
                        asyncio.create_task(_safe_handler())
                else:
                    handler(channel, payload)
            except Exception as err:
                logger.error("EventBus handler error for %s: %s", channel, err)
        
        # Publish to all streaming subscribers
        for queue in self._event_queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("[EventBus] Dropped event for full stream queue: %s", channel)

    def subscribe_stream(self) -> asyncio.Queue[dict[str, Any]]:
        """Create a new queue for streaming subscribers."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._event_queues.append(queue)
        return queue

    def unsubscribe_stream(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a streaming subscriber."""
        if queue in self._event_queues:
            self._event_queues.remove(queue)

    def clear(self) -> None:
        with self._lock:
            self._subscribers.clear()
            self._event_queues.clear()

# Global Singleton
event_bus = EventBus()

# Compatibility functions (mapping to global instance)
def subscribe(event: str, callback: Callable) -> None:
    event_bus.subscribe(event, callback)

def unsubscribe(event: str, callback: Callable) -> None:
    event_bus.unsubscribe(event, callback)

def fire_event(event: str, data=None) -> None:
    payload = data if isinstance(data, dict) else {"data": data}
    event_bus.publish(event, payload)

def get_task_scheduler():
    try:
        from core.scheduler import scheduler
        return scheduler
    except ImportError:
        logger.warning("scheduler not available")
        return None
