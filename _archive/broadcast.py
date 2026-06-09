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

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[str, Any], Awaitable[None]]


class EventBroadcaster:
    """Scope-guarded WebSocket event broadcaster for real-time dashboard updates.

    Patterns borrowed from OpenClaw's createGatewayBroadcaster.
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable[[str, Any], Awaitable[None]]]] = {}
        self._seq = 0

    def subscribe(self, scope: str, handler: Callable[[str, Any], Awaitable[None]]) -> None:
        self._subscribers.setdefault(scope, []).append(handler)

    def unsubscribe(self, scope: str, handler: Callable[[str, Any], Awaitable[None]]) -> None:
        handlers = self._subscribers.get(scope, [])
        if handler in handlers:
            handlers.remove(handler)

    async def broadcast(self, event: str, payload: Any, scope: str = "default") -> int:
        self._seq += 1
        frame = {
            "type": "event",
            "event": event,
            "payload": payload,
            "seq": self._seq,
            "ts": time.time(),
        }
        handlers = self._subscribers.get(scope, []) + self._subscribers.get("*", [])
        for handler in handlers:
            try:
                await handler(event, frame)
            except Exception as e:
                logger.exception("[BROADCAST] Handler error: %s", e)
        return self._seq

    async def broadcast_to_all(self, event: str, payload: Any) -> int:
        return await self.broadcast(event, payload, scope="*")


broadcaster = EventBroadcaster()
