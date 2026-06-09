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

import logging
from typing import Any

from .base import ChannelPlugin, ChannelConfig

logger = logging.getLogger(__name__)


class ChannelController:
    def __init__(self):
        self._channels: dict[str, ChannelPlugin] = {}
        self._brain: Any = None

    def register(self, channel: ChannelPlugin) -> None:
        self._channels[channel.id] = channel
        logger.info("[Channels] Registered: %s", channel.id)

    def get(self, channel_id: str) -> ChannelPlugin | None:
        return self._channels.get(channel_id)

    @property
    def channels(self) -> dict[str, ChannelPlugin]:
        return dict(self._channels)

    @property
    def running(self) -> list[ChannelPlugin]:
        return [c for c in self._channels.values() if c.is_running]

    async def start_all(self, brain: Any) -> None:
        self._brain = brain
        for cid, channel in self._channels.items():
            try:
                await channel.start(brain)
            except Exception as e:
                logger.exception("[Channels] Failed to start %s: %s", cid, e)

        active = [c.name for c in self._channels.values() if c.is_running]
        logger.info("[Channels] Running: %s", active or "(none)")

    async def stop_all(self) -> None:
        for cid, channel in self._channels.items():
            try:
                await channel.stop()
            except Exception as e:
                logger.warning("[Channels] Error stopping %s: %s", cid, e)
        logger.info("[Channels] All stopped")

    async def send(self, channel_id: str, target: str, message: str) -> bool:
        channel = self._channels.get(channel_id)
        if not channel:
            logger.warning("[Channels] Unknown channel: %s", channel_id)
            return False
        return await channel.send(target, message)
