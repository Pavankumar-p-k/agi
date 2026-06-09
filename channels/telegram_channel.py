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
import os

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from .base import ChannelPlugin, ChannelConfig
from .processor import process_message

logger = logging.getLogger(__name__)


class TelegramChannel(ChannelPlugin):
    id = "telegram"
    name = "Telegram"
    description = "Telegram bot integration via python-telegram-bot"

    def __init__(self, config: ChannelConfig | None = None):
        super().__init__(config)
        self._app: Application | None = None

    async def start(self, brain) -> None:
        await super().start(brain)
        token = self.config.token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            logger.warning("[Telegram] No token configured — channel disabled")
            self._running = False
            return

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return
            text = update.message.text.strip()
            user = update.effective_user
            chat_id = update.effective_chat.id if update.effective_chat else 0
            user_id = str(user.id) if user else "0"
            user_name = user.full_name if user else "Unknown"

            # Access Control Check
            if not self.check_access(user_id):
                # Check for pairing response
                if self.pairing.verify_response(user_id, text):
                    self.config.allowlist.add(user_id)
                    await context.bot.send_message(chat_id=chat_id, text="Pairing successful! You are now authorized.")
                    return
                
                # Offer pairing if it's a private chat
                from telegram.constants import ChatType
                if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
                    challenge = self.pairing.create_challenge(user_id)
                    await context.bot.send_message(
                        chat_id=chat_id, 
                        text=f"Access Denied. To pair this account, please reply with this code: {challenge}"
                    )
                return

            reply = await process_message(
                text=text,
                source="telegram",
                channel_id=str(chat_id),
                user_id=user_id,
                user_name=user_name,
            )

            await context.bot.send_message(chat_id=chat_id, text=reply[:4096])

        self._app = Application.builder().token(token).build()
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        self._running = True
        try:
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling()
            logger.info("[Telegram] Connected")
        except Exception as e:
            logger.exception("[Telegram] Connection failed: %s", e)
            self._running = False

    async def stop(self) -> None:
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.warning("[Telegram] Shutdown error: %s", e)
            self._app = None
        await super().stop()

    async def send(self, target: str, message: str) -> bool:
        try:
            token = self.config.token or os.getenv("TELEGRAM_BOT_TOKEN", "")
            from telegram import Bot
            bot = Bot(token=token)
            await bot.send_message(chat_id=int(target), text=message[:4096])
            return True
        except Exception as e:
            logger.warning("[Telegram] Send failed: %s", e)
            return False
