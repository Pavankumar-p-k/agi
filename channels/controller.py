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
