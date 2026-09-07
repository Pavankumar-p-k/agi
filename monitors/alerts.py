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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Awaitable, Callable, Optional

logger = logging.getLogger("jarvis.monitors.alerts")


class AlertPriority(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    priority: AlertPriority
    module: str
    message: str
    voice_summary: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class AlertRouter:
    """Unified alert routing — WebSocket broadcast, TTS, WhatsApp.

    Replaces: proactive_monitor (SystemMonitor, BuildMonitor, notification dispatch).
    """

    def __init__(
        self,
        broadcast_fn: Optional[Callable[[str], Awaitable[None]]] = None,
        speak_fn: Optional[Callable[[str], Awaitable[None]]] = None,
        whatsapp_fn: Optional[Callable[[str], None]] = None,
    ):
        self._broadcast_fn = broadcast_fn
        self._speak_fn = speak_fn
        self._whatsapp_fn = whatsapp_fn
        self._history: list[Alert] = []
        self._max_history = 100

    def send(self, alert: Alert) -> None:
        """Dispatch an alert through all available channels."""
        self._history.append(alert)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        logger.warning("[ALERT] [%s] %s: %s", alert.priority, alert.module, alert.message)

        # Fire-and-forget broadcast
        if self._broadcast_fn:
            asyncio.ensure_future(self._broadcast_fn(alert.message))

        # Voice alerts for critical + warning
        if self._speak_fn and alert.priority in (AlertPriority.CRITICAL, AlertPriority.WARNING):
            text = alert.voice_summary or alert.message
            asyncio.ensure_future(self._speak_fn(text))

        # WhatsApp for all non-info alerts
        if self._whatsapp_fn and alert.priority != AlertPriority.INFO:
            try:
                self._whatsapp_fn(f"[{alert.priority}] {alert.module}: {alert.message}")
            except Exception as e:
                logger.warning("[ALERT] WhatsApp send failed: %s", e)

    def get_history(self, n: int = 20) -> list[Alert]:
        return self._history[-n:]


alert_router = AlertRouter()
