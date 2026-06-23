"""tools/whatsapp_sender.py
Backward-compatible wrapper around the production WhatsApp provider.
Delegates to integrations.whatsapp.WhatsAppCloudAPIProvider.
Used by ProactiveMonitor for alert dispatch and by routers/whatsapp.py for replies.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_cloud_provider = None


async def _get_provider():
    global _cloud_provider
    if _cloud_provider is None:
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        _cloud_provider = WhatsAppCloudAPIProvider()
        ok = await _cloud_provider.connect()
        if not ok:
            logger.warning("[WHATSAPP] Cloud API provider failed to connect")
    return _cloud_provider


class WhatsAppSender:
    def __init__(self):
        self._token = os.getenv("META_WHATSAPP_TOKEN", "")
        self._phone_id = os.getenv("META_WHATSAPP_PHONE_ID", "")

    @property
    def ready(self) -> bool:
        return bool(self._token and self._phone_id)

    async def health_check(self) -> bool:
        if not self.ready:
            return False
        try:
            provider = await _get_provider()
            if provider:
                return await provider.health_check()
        except Exception as e:
            logger.warning("[WHATSAPP] Health check error: %s", e)
        return False

    async def send(self, to: str, message: str) -> bool:
        if not self.ready:
            logger.debug("[WHATSAPP] Not configured — skipping send")
            return False
        try:
            provider = await _get_provider()
            if not provider:
                return False
            result = await provider.send_text(to, message)
            if result.success:
                logger.info("[WHATSAPP] Sent to %s: %.60s", to, message)
                return True
            logger.warning("[WHATSAPP] Send failed: %s", result.error)
            return False
        except Exception as e:
            logger.warning("[WHATSAPP] Send error: %s", e)
            return False


whatsapp_sender = WhatsAppSender()
