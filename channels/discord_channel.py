"""Discord channel — connects a discord.py client and relays messages."""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
from typing import Any, Optional

import discord

from channels.base import ChannelConfig, ChannelPlugin

logger = logging.getLogger(__name__)


class DiscordChannel(ChannelPlugin):
    """Discord bot channel (token from config or ``DISCORD_BOT_TOKEN``)."""

    id = "discord"
    name = "Discord"

    def __init__(self, config: Optional[ChannelConfig] = None,
                 handler: Any = None) -> None:
        super().__init__(config, handler)
        self._client: Any = None
        self._task: Any = None

    def _token(self) -> str:
        return self.config.token or os.getenv("DISCORD_BOT_TOKEN", "")

    async def start(self, app: Any = None) -> None:
        self._app = app
        token = self._token()
        if not token:
            self.is_running = False
            return
        try:
            intents = discord.Intents.default()
            self._client = discord.Client(intents=intents)
            self._task = asyncio.create_task(self._client.start(token))
            self.is_running = True
        except Exception as exc:  # noqa: BLE001 — honest failure
            logger.warning("[discord] start failed: %s", exc)
            self.is_running = False

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            try:
                task.cancel()
            except Exception:  # noqa: BLE001
                pass
        client, self._client = self._client, None
        if client is not None:
            try:
                close = getattr(client, "close", None)
                if close is not None:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
            except Exception:  # noqa: BLE001
                pass
        self.is_running = False

    async def send(self, target: str, message: str) -> bool:
        if self._client is None:
            return False
        try:
            get_channel = getattr(self._client, "get_channel", None)
            channel = None
            if get_channel is not None:
                channel = get_channel(int(target) if str(target).isdigit() else target)
                if inspect.isawaitable(channel):
                    channel = await channel
            send = getattr(channel, "send", None)
            if send is None:
                return False
            result = send(str(message))
            if inspect.isawaitable(result):
                await result
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("[discord] send failed: %s", exc)
            return False


__all__ = ["DiscordChannel"]
