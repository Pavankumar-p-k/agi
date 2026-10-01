"""Slack channel — Socket Mode client + Web API for outbound messages."""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import threading
from typing import Any, Optional

from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.web.async_client import AsyncWebClient as WebClient

from channels.base import ChannelConfig, ChannelPlugin

logger = logging.getLogger(__name__)


class SlackChannel(ChannelPlugin):
    """Slack channel (bot + app tokens from config or ``SLACK_*`` env vars)."""

    id = "slack"
    name = "Slack"

    def __init__(self, config: Optional[ChannelConfig] = None,
                 handler: Any = None) -> None:
        super().__init__(config, handler)
        self._client: Any = None
        self._socket_client: Any = None
        self._thread: Any = None

    def _tokens(self) -> tuple[str, str]:
        extra = self.config.extra or {}
        bot = self.config.token or os.getenv("SLACK_BOT_TOKEN", "")
        app = str(extra.get("app_token") or os.getenv("SLACK_APP_TOKEN", ""))
        return bot, app

    async def start(self, app: Any = None) -> None:
        self._app = app
        bot_token, app_token = self._tokens()
        if not bot_token or not app_token:
            self.is_running = False
            return
        try:
            self._client = WebClient(token=bot_token)
            self._socket_client = SocketModeClient(
                app_token=app_token, web_client=self._client)
            # The socket-mode client owns a blocking loop; run it off-thread.
            self._thread = threading.Thread(target=self._run_socket, daemon=True)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and loop.is_running():
                self._thread.start()
            self.is_running = True
        except Exception as exc:  # noqa: BLE001 — honest failure
            logger.warning("[slack] start failed: %s", exc)
            self.is_running = False

    def _run_socket(self) -> None:
        connector = getattr(self._socket_client, "connect", None)
        if connector is None:
            return
        try:
            connector()
        except Exception as exc:  # noqa: BLE001 — thread must not raise loudly
            logger.debug("[slack] socket connect ended: %s", exc)

    async def stop(self) -> None:
        socket_client, self._socket_client = self._socket_client, None
        if socket_client is not None:
            try:
                close = getattr(socket_client, "close", None)
                if close is not None:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
            except Exception:  # noqa: BLE001
                pass
        self._thread = None
        self._client = None
        self.is_running = False

    async def send(self, target: str, message: str) -> bool:
        if self._client is None:
            return False
        try:
            result = self._client.chat_postMessage(channel=target, text=str(message))
            if inspect.isawaitable(result):
                await result
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("[slack] send failed: %s", exc)
            return False


__all__ = ["SlackChannel", "SocketModeClient", "WebClient"]
