"""ChannelController — registry and lifecycle owner for channel plugins."""
from __future__ import annotations

import logging
from typing import Any, Optional

from channels.base import ChannelPlugin

logger = logging.getLogger(__name__)


class ChannelController:
    """Registers channel plugins and fans lifecycle/send calls out to them."""

    def __init__(self) -> None:
        self._channels: dict[str, ChannelPlugin] = {}

    # ── registration ─────────────────────────────────────────────────
    def register(self, plugin: ChannelPlugin) -> ChannelPlugin:
        self._channels[plugin.id] = plugin
        return plugin

    def unregister(self, channel_id: str) -> bool:
        return self._channels.pop(channel_id, None) is not None

    def get(self, channel_id: str) -> Optional[ChannelPlugin]:
        return self._channels.get(channel_id)

    @property
    def channels(self) -> dict[str, ChannelPlugin]:
        return self._channels

    @property
    def running(self) -> list[str]:
        return [cid for cid, plugin in self._channels.items() if plugin.is_running]

    # ── lifecycle ────────────────────────────────────────────────────
    async def start(self, channel_id: str, app: Any = None) -> bool:
        plugin = self._channels.get(channel_id)
        if plugin is None:
            return False
        await plugin.start(app)
        return True

    async def stop(self, channel_id: str) -> bool:
        plugin = self._channels.get(channel_id)
        if plugin is None:
            return False
        await plugin.stop()
        return True

    async def start_all(self, app: Any = None) -> list[str]:
        started: list[str] = []
        for channel_id, plugin in list(self._channels.items()):
            try:
                await plugin.start(app)
                started.append(channel_id)
            except Exception as exc:  # noqa: BLE001 — one channel must not block others
                logger.warning("[channels] %s failed to start: %s", channel_id, exc)
        return started

    async def stop_all(self) -> None:
        for channel_id, plugin in list(self._channels.items()):
            try:
                await plugin.stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[channels] %s failed to stop: %s", channel_id, exc)

    # ── outbound ─────────────────────────────────────────────────────
    async def send(self, channel_id: str, target: str, message: str) -> bool:
        plugin = self._channels.get(channel_id)
        if plugin is None:
            return False
        try:
            return bool(await plugin.send(target, message))
        except NotImplementedError:
            logger.debug("[channels] %s has no send()", channel_id)
            return False
        except Exception as exc:  # noqa: BLE001 — sends fail honestly
            logger.warning("[channels] %s send failed: %s", channel_id, exc)
            return False

    def to_dict(self) -> dict:
        return {
            cid: {"id": cid, "name": plugin.name,
                  "enabled": plugin.enabled, "running": plugin.is_running}
            for cid, plugin in self._channels.items()
        }


channel_controller = ChannelController()


__all__ = ["ChannelController", "channel_controller"]
