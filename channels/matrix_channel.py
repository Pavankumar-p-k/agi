"""Matrix channel — matrix-nio client with login or access-token auth."""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
from typing import Any, Optional

from nio import AsyncClient, LoginResponse

from channels.base import ChannelConfig, ChannelPlugin

logger = logging.getLogger(__name__)


class MatrixChannel(ChannelPlugin):
    """Matrix channel (homeserver/user/password or access token)."""

    id = "matrix"
    name = "Matrix"

    def __init__(self, config: Optional[ChannelConfig] = None,
                 handler: Any = None) -> None:
        super().__init__(config, handler)
        self._client: Any = None
        self._task: Any = None

    def _creds(self) -> tuple[str, str, str, str]:
        extra = self.config.extra or {}
        homeserver = str(extra.get("homeserver") or os.getenv("MATRIX_HOMESERVER", ""))
        user_id = str(extra.get("user_id") or os.getenv("MATRIX_USER_ID", ""))
        password = str(extra.get("password") or os.getenv("MATRIX_PASSWORD", ""))
        token = self.config.token or os.getenv("MATRIX_ACCESS_TOKEN", "")
        return homeserver, user_id, password, token

    async def start(self, app: Any = None) -> None:
        self._app = app
        homeserver, user_id, password, token = self._creds()
        if not homeserver or (not (user_id and password) and not token):
            self.is_running = False
            return
        try:
            client = AsyncClient(homeserver, user_id or None)
            if token:
                client.access_token = token
            else:
                response = await client.login(password)
                if not isinstance(response, LoginResponse):
                    logger.warning("[matrix] login failed: %s", response)
                    self.is_running = False
                    return
            self._client = client
            self._task = asyncio.create_task(self._sync(client))
            self.is_running = True
        except Exception as exc:  # noqa: BLE001 — honest failure
            logger.warning("[matrix] start failed: %s", exc)
            self.is_running = False

    @staticmethod
    async def _sync(client: Any) -> None:
        sync_forever = getattr(client, "sync_forever", None)
        if sync_forever is None:
            return
        try:
            await sync_forever()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.debug("[matrix] sync ended: %s", exc)

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
                result = client.close()
                if inspect.isawaitable(result):
                    await result
            except Exception:  # noqa: BLE001
                pass
        self.is_running = False

    async def send(self, target: str, message: str) -> bool:
        if self._client is None:
            return False
        try:
            result = self._client.room_send(
                room_id=target,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": str(message)},
            )
            if inspect.isawaitable(result):
                await result
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("[matrix] send failed: %s", exc)
            return False


__all__ = ["MatrixChannel", "AsyncClient", "LoginResponse"]
