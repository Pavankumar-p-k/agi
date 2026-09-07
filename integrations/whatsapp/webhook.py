"""integrations/whatsapp/webhook.py
WhatsApp webhook handler with HMAC-SHA256 signature verification,
media processing, status callbacks, and message buffering.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from collections import deque
from datetime import datetime
from typing import Any, Callable

from .models import MessageStatus, MessageType, WhatsAppMessage

logger = logging.getLogger(__name__)


class WhatsAppWebhookHandler:
    def __init__(self, app_secret: str = "", verify_token: str = "", max_buffer: int = 100):
        self._app_secret = app_secret or os.getenv("META_APP_SECRET", "")
        self._verify_token = verify_token or os.getenv("META_VERIFY_TOKEN", "")
        self._message_buffer: deque[WhatsAppMessage] = deque(maxlen=max_buffer)
        self._last_status: dict[str, MessageStatus] = {}
        self._on_message: Callable[[WhatsAppMessage], None] | None = None
        self._on_status: Callable[[WhatsAppMessage], None] | None = None

    def set_on_message(self, callback: Callable[[WhatsAppMessage], None]):
        self._on_message = callback

    def set_on_status(self, callback: Callable[[WhatsAppMessage], None]):
        self._on_status = callback

    def verify_signature(self, body: bytes, signature_header: str | None) -> bool:
        if not self._app_secret:
            logger.warning("[WhatsApp Webhook] No app secret configured — skipping signature verification")
            return True
        if not signature_header:
            logger.warning("[WhatsApp Webhook] Missing X-Hub-Signature-256 header")
            return False
        expected = hmac.new(
            self._app_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        provided = signature_header.replace("sha256=", "").strip()
        return hmac.compare_digest(expected, provided)

    def verify_webhook_token(self, mode: str, token: str, challenge: str) -> str | None:
        if mode == "subscribe" and token == self._verify_token:
            logger.info("[WhatsApp Webhook] Verification successful")
            return challenge
        logger.warning("[WhatsApp Webhook] Verification failed: mode=%s", mode)
        return None

    def process_incoming(self, body: dict, business_phone: str = "") -> list[WhatsAppMessage]:
        messages: list[WhatsAppMessage] = []
        try:
            entry = body.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])
            for change in changes:
                value = change.get("value", {})
                if "messages" in value:
                    for msg_data in value["messages"]:
                        msg = WhatsAppMessage.from_webhook_payload(
                            {"message": msg_data, "from": msg_data.get("from", "")},
                            business_phone or value.get("metadata", {}).get("display_phone_number", ""),
                        )
                        messages.append(msg)
                        self._message_buffer.append(msg)
                        if self._on_message:
                            self._on_message(msg)
                if "statuses" in value:
                    for status_data in value["statuses"]:
                        status_msg_id = status_data.get("id", "")
                        status = MessageStatus(status_data.get("status", "pending"))
                        self._last_status[status_msg_id] = status
                        if self._on_status:
                            status_msg = WhatsAppMessage.from_status_payload(
                                {"status": {"statuses": [status_data]}}
                            )
                            self._on_status(status_msg)
        except Exception as e:
            logger.warning("[WhatsApp Webhook] Processing error: %s", e)
        return messages

    def get_buffered_messages(self, clear: bool = True, limit: int = 20) -> list[WhatsAppMessage]:
        if clear:
            result = list(self._message_buffer)[:limit]
            self._message_buffer.clear()
            return result
        return list(self._message_buffer)[-limit:]

    def get_message_status(self, message_id: str) -> MessageStatus | None:
        return self._last_status.get(message_id)

    def requires_media_download(self, msg: WhatsAppMessage) -> bool:
        return msg.type in (
            MessageType.IMAGE,
            MessageType.AUDIO,
            MessageType.VOICE,
            MessageType.VIDEO,
            MessageType.DOCUMENT,
        ) and msg.media is not None

    def requires_text_reply(self, msg: WhatsAppMessage) -> bool:
        return msg.type in (
            MessageType.TEXT,
            MessageType.INTERACTIVE,
            MessageType.BUTTON,
            MessageType.LOCATION,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self._verify_token)
