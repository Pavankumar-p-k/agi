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
import logging
from typing import Any, Callable, AsyncGenerator
from collections import deque

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], Any]]] = {}
        self._event_queues: list[asyncio.Queue[dict[str, Any]]] = []

    def subscribe(self, channel: str, callback: Callable[[dict[str, Any]], Any]) -> None:
        self._subscribers.setdefault(channel, []).append(callback)

    def publish(self, channel: str, payload: dict[str, Any]) -> None:
        # Wrap payload with channel info for streaming
        event = {"channel": channel, **payload}
        
        # Notify all sync subscribers
        if channel in self._subscribers:
            for subscriber in self._subscribers[channel]:
                try:
                    result = subscriber(payload)
                    if asyncio.iscoroutine(result):
                        asyncio.create_task(result)
                except Exception as err:
                    import logging
                    logging.getLogger(__name__).error("Subscriber error: %s", err)
        
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
        self._subscribers.clear()
        self._event_queues.clear()

# Global Event Bus
event_bus = EventBus()
