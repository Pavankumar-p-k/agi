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
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class PluginEventBus:
    _instance: PluginEventBus | None = None

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._history: list[dict] = []
        self._max_history = 100

    @classmethod
    def instance(cls) -> PluginEventBus:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._subscribers[event_type].append(handler)
        logger.debug("[EventBus] Subscribed %s to %s", getattr(handler, "__name__", "?"), event_type)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        self._subscribers[event_type] = [h for h in self._subscribers[event_type] if h is not handler]

    async def emit(self, event_type: str, **data: Any) -> list[Any]:
        results = []
        for handler in self._subscribers.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    r = await handler(event_type=event_type, **data)
                else:
                    r = handler(event_type=event_type, **data)
                results.append(r)
            except Exception as e:
                logger.exception("[EventBus] Handler %s failed on %s: %s", handler.__name__, event_type, e)

        try:
            from core.plugins.base import plugin_registry
            await plugin_registry.run_hook(event_type, **data)
        except Exception as _e:
            logger.debug("plugins events emit run_hook failed: %s", _e)

        self._history.append({"type": event_type, "data": data})
        if len(self._history) > self._max_history:
            self._history.pop(0)
        return results

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()
