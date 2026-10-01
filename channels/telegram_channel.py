"""Telegram channel — python-telegram-bot polling application."""
from __future__ import annotations

import inspect
import logging
import os
from typing import Any, Optional

from telegram.ext import Application

from channels.base import ChannelConfig, ChannelPlugin

logger = logging.getLogger(__name__)


class TelegramChannel(ChannelPlugin):
    """Telegram bot channel (token from config or ``TELEGRAM_BOT_TOKEN``)."""

    id = "telegram"
    name = "Telegram"

    def __init__(self, config: Optional[ChannelConfig] = None,
                 handler: Any = None) -> None:
        super().__init__(config, handler)

    def _token(self) -> str:
        return self.config.token or os.getenv("TELEGRAM_BOT_TOKEN", "")

    async def start(self, app: Any = None) -> None:
        token = self._token()
        if not token:
            self.is_running = False
            return
        try:
            application = Application.builder().token(token).build()
            await application.initialize()
            await application.start()
            updater = getattr(application, "updater", None)
            if updater is not None:
                await updater.start_polling()
            self._app = application
            self.is_running = True
        except Exception as exc:  # noqa: BLE001 — honest failure
            logger.warning("[telegram] start failed: %s", exc)
            self.is_running = False

    async def stop(self) -> None:
        application, self._app = self._app, None
        if application is not None:
            try:
                updater = getattr(application, "updater", None)
                if updater is not None:
                    await updater.stop()
                await application.stop()
                await application.shutdown()
            except Exception:  # noqa: BLE001
                pass
        self.is_running = False

    async def send(self, target: str, message: str) -> bool:
        application = self._app
        if application is None:
            return False
        bot = getattr(application, "bot", None)
        if bot is None:
            return False
        try:
            result = bot.send_message(chat_id=target, text=str(message))
            if inspect.isawaitable(result):
                await result
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("[telegram] send failed: %s", exc)
            return False


__all__ = ["TelegramChannel", "Application"]
