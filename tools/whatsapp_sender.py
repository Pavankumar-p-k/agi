"""tools/whatsapp_sender.py
Meta Cloud API WhatsApp sender — no browser, no Selenium.
Used by ProactiveMonitor for alert dispatch and by routers/whatsapp.py for replies.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

META_API_BASE = "https://graph.facebook.com/v18.0"


class WhatsAppSender:
    def __init__(self):
        self._token = os.getenv("META_WHATSAPP_TOKEN", "")
        self._phone_id = os.getenv("META_WHATSAPP_PHONE_ID", "")

    @property
    def ready(self) -> bool:
        return bool(self._token and self._phone_id)

    async def send(self, to: str, message: str) -> bool:
        if not self.ready:
            logger.debug("[WHATSAPP] Not configured — skipping send")
            return False
        url = f"{META_API_BASE}/{self._phone_id}/messages"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "messaging_product": "whatsapp",
                        "to": to,
                        "type": "text",
                        "text": {"body": message[:4096]},
                    },
                )
                if r.status_code == 200:
                    logger.info("[WHATSAPP] Sent to %s: %.60s", to, message)
                    return True
                logger.warning("[WHATSAPP] Send failed: %d %s", r.status_code, r.text[:200])
                return False
        except Exception as e:
            logger.warning("[WHATSAPP] Send error: %s", e)
            return False


whatsapp_sender = WhatsAppSender()
