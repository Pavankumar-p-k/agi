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
# core/cloud/realtime_sync.py
# RealtimeSync — subscribes to Supabase Realtime changes on jarvis_memories.
from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from typing import Any

from .supabase_client import get_client, is_connected

logger = logging.getLogger("jarvis.cloud.realtime")


class RealtimeSync:
    """
    Thin wrapper around supabase-py Realtime channels.
    Falls back gracefully if Supabase is not available.
    """

    def __init__(self):
        self._subscriptions: dict[str, Any] = {}   # id → channel
        self._running = False
        self._thread: threading.Thread | None = None

    def subscribe(self, table: str, callback: Callable[[str, dict], None]) -> str:
        """
        Subscribe to INSERT / UPDATE / DELETE on *table*.
        callback(event_type, record) is called on changes.
        Returns a subscription_id you can use to unsubscribe.
        """
        if not is_connected():
            logger.warning("RealtimeSync.subscribe: Supabase not connected")
            return ""

        sub_id = str(uuid.uuid4())
        try:
            client = get_client()
            channel = (
                client.channel(f"jarvis:{table}:{sub_id}")
                .on(
                    "postgres_changes",
                    event="*",
                    schema="public",
                    table=table,
                    callback=lambda payload: callback(
                        payload.get("eventType", "UNKNOWN"),
                        payload.get("new") or payload.get("old") or {},
                    ),
                )
                .subscribe()
            )
            self._subscriptions[sub_id] = channel
            logger.info("Subscribed to %s (id=%s)", table, sub_id)
        except Exception as exc:
            logger.error("RealtimeSync.subscribe failed: %s", exc)
            return ""
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        channel = self._subscriptions.pop(subscription_id, None)
        if channel is None:
            return
        try:
            client = get_client()
            if client:
                client.remove_channel(channel)
        except Exception as exc:
            logger.warning("Could not remove channel: %s", exc)

    def start(self) -> None:
        """No-op: supabase-py manages its own event loop for realtime."""
        self._running = True
        logger.info("RealtimeSync started")

    def stop(self) -> None:
        """Unsubscribe all channels."""
        for sub_id in list(self._subscriptions.keys()):
            self.unsubscribe(sub_id)
        self._running = False
        logger.info("RealtimeSync stopped")


# Singleton
_realtime: RealtimeSync | None = None


def get_realtime_sync() -> RealtimeSync:
    global _realtime
    if _realtime is None:
        _realtime = RealtimeSync()
    return _realtime
