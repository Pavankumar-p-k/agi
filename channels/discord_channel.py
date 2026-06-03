from __future__ import annotations

import asyncio
import logging
import os

from .base import ChannelPlugin, ChannelConfig
from .processor import process_message

logger = logging.getLogger(__name__)


class DiscordChannel(ChannelPlugin):
    id = "discord"
    name = "Discord"
    description = "Discord bot integration via discord.py"

    def __init__(self, config: ChannelConfig | None = None):
        super().__init__(config)
        self._client = None
        self._task = None

    async def start(self, brain) -> None:
        await super().start(brain)
        token = self.config.token or os.getenv("DISCORD_TOKEN", "")
        if not token:
            logger.warning("[Discord] No token configured — channel disabled")
            self._running = False
            return

        import discord
        intents = discord.Intents.default()
        intents.message_content = True

        class JarvisBot(discord.Client):
            def __init__(self, channel: DiscordChannel):
                super().__init__(intents=intents)
                self._channel_ref = channel

            async def on_ready(self):
                logger.info("[Discord] Logged in as %s", self.user)

            async def on_message(self, message):
                if message.author == self.user:
                    return
                if self.user not in message.mentions:
                    return
                text = message.content
                for mention in message.mentions:
                    text = text.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "").strip()
                if not text:
                    return
                async with message.channel.typing():
                    reply = await process_message(
                        text=text,
                        source="discord",
                        channel_id=str(message.channel.id),
                        user_id=str(message.author.id),
                        user_name=str(message.author),
                    )
                await message.reply(reply[:2000], mention_author=False)

        self._client = JarvisBot(self)
        self._running = True
        self._task = asyncio.create_task(self._run_client(token))

    async def _run_client(self, token: str):
        try:
            await self._client.start(token)
        except Exception as e:
            logger.exception("[Discord] Connection failed: %s", e)
            self._running = False

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client:
            await self._client.close()
            self._client = None
        await super().stop()

    async def send(self, target: str, message: str) -> bool:
        import discord
        try:
            channel = self._client.get_channel(int(target))
            if channel:
                await channel.send(message[:2000])
                return True
            logger.warning("[Discord] Channel %s not found", target)
            return False
        except Exception as e:
            logger.warning("[Discord] Send failed: %s", e)
            return False
