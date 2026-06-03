from __future__ import annotations

import asyncio
import logging
import os

from nio import AsyncClient, RoomMessageText, LoginResponse

from .base import ChannelPlugin, ChannelConfig
from .processor import process_message

logger = logging.getLogger(__name__)


class MatrixChannel(ChannelPlugin):
    id = "matrix"
    name = "Matrix"
    description = "Matrix chat integration via matrix-nio"

    def __init__(self, config: ChannelConfig | None = None):
        super().__init__(config)
        self._client: AsyncClient | None = None
        self._task = None

    async def start(self, brain) -> None:
        await super().start(brain)
        homeserver = self.config.extra.get("homeserver") or os.getenv("MATRIX_HOMESERVER", "https://matrix.org")
        user_id = self.config.extra.get("user_id") or os.getenv("MATRIX_USER_ID", "")
        password = self.config.extra.get("password") or os.getenv("MATRIX_PASSWORD", "")
        if not user_id or not password:
            logger.warning("[Matrix] MATRIX_USER_ID or MATRIX_PASSWORD not set — channel disabled")
            self._running = False
            return

        self._client = AsyncClient(homeserver, user_id)
        resp = await self._client.login(password)
        if not isinstance(resp, LoginResponse):
            logger.warning("[Matrix] Login failed: %s", resp)
            self._running = False
            return

        async def message_callback(room, event):
            if event.sender == self._client.user_id:
                return
            text = event.body
            if not text:
                return

            reply = await process_message(
                text=text,
                source="matrix",
                channel_id=room.room_id,
                user_id=event.sender,
                user_name=event.sender,
            )

            await self._client.room_send(
                room_id=room.room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": reply[:4000]},
            )

        self._client.add_event_callback(message_callback, RoomMessageText)

        self._running = True
        self._task = asyncio.create_task(self._run_sync())

    async def _run_sync(self):
        try:
            await self._client.sync_forever(timeout=30000)
        except Exception as e:
            logger.exception("[Matrix] Sync failed: %s", e)
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
        try:
            if self._client:
                await self._client.room_send(
                    room_id=target,
                    message_type="m.room.message",
                    content={"msgtype": "m.text", "body": message[:4000]},
                )
                return True
        except Exception as e:
            logger.warning("[Matrix] Send failed: %s", e)
        return False
