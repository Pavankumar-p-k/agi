from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .base import BaseWhatsAppProvider
from .models import SendResult
from .retry import AsyncRetry

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


class TwilioWhatsAppProvider(BaseWhatsAppProvider):
    name = "twilio_whatsapp"

    def __init__(self):
        super().__init__()
        self._account_sid: str = ""
        self._auth_token: str = ""
        self._from_number: str = ""
        self._http: httpx.AsyncClient | None = None
        self._retry = AsyncRetry(max_attempts=3, base_delay=1.0, retryable_exceptions=(httpx.HTTPError,))

    async def connect(self, **kwargs) -> bool:
        self._account_sid = kwargs.get("account_sid", "") or os.getenv("TWILIO_ACCOUNT_SID", "")
        self._auth_token = kwargs.get("auth_token", "") or os.getenv("TWILIO_AUTH_TOKEN", "")
        self._from_number = kwargs.get("from_number", "") or os.getenv("TWILIO_WHATSAPP_FROM", "")
        if not self._account_sid or not self._auth_token or not self._from_number:
            logger.warning("[Twilio WhatsApp] Missing account_sid, auth_token, or from_number")
            return False
        self._http = httpx.AsyncClient(timeout=15)
        ok = await self.health_check()
        if ok:
            self._connected = True
            logger.info("[Twilio WhatsApp] Connected — %s", self._from_number)
        return ok

    async def disconnect(self) -> bool:
        self._connected = False
        if self._http:
            await self._http.aclose()
            self._http = None
        return True

    def _format_number(self, number: str) -> str:
        if not number.startswith("whatsapp:"):
            return f"whatsapp:{number}"
        return number

    async def send_text(self, to: str, text: str, **kwargs) -> SendResult:
        data = {
            "To": self._format_number(to),
            "From": self._format_number(self._from_number),
            "Body": text[:4096],
        }
        if kwargs.get("context_message_id"):
            data["PersistentAction"] = f"context={kwargs['context_message_id']}"
        return await self._post(data)

    async def send_image(self, to: str, image_url: str, caption: str | None = None, **kwargs) -> SendResult:
        data = {
            "To": self._format_number(to),
            "From": self._format_number(self._from_number),
            "MediaUrl": image_url,
        }
        if caption:
            data["Body"] = caption[:1024] if caption else ""
        return await self._post(data)

    async def send_document(self, to: str, document_url: str, filename: str, caption: str | None = None, **kwargs) -> SendResult:
        data = {
            "To": self._format_number(to),
            "From": self._format_number(self._from_number),
            "MediaUrl": document_url,
        }
        if caption:
            data["Body"] = caption[:1024]
        return await self._post(data)

    async def send_audio(self, to: str, audio_url: str, **kwargs) -> SendResult:
        data = {
            "To": self._format_number(to),
            "From": self._format_number(self._from_number),
            "MediaUrl": audio_url,
        }
        return await self._post(data)

    async def send_location(self, to: str, latitude: float, longitude: float, name: str | None = None, address: str | None = None, **kwargs) -> SendResult:
        body_parts = [f"https://maps.google.com/?q={latitude},{longitude}"]
        if name:
            body_parts.insert(0, name)
        if address:
            body_parts.append(address)
        return await self.send_text(to, "\n".join(body_parts))

    async def _post(self, data: dict) -> SendResult:
        if not self._http:
            return SendResult(success=False, error="Not connected", provider=self.name)
        try:
            result, attempts = await self._retry.execute(
                self._do_post, data, on_retry=self._on_retry
            )
            return result
        except Exception as e:
            return SendResult(success=False, error=str(e), retry_attempts=3, provider=self.name)

    async def _do_post(self, data: dict) -> SendResult:
        url = f"{TWILIO_API_BASE}/Accounts/{self._account_sid}/Messages.json"
        auth = (self._account_sid, self._auth_token)
        resp = await self._http.post(url, auth=auth, data=data)
        if resp.status_code == 201:
            resp_data = resp.json()
            msg_id = resp_data.get("sid", "")
            return SendResult(success=True, message_id=msg_id, provider=self.name)
        error_body = resp.text[:500]
        logger.warning("[Twilio WhatsApp] POST failed: %d %s", resp.status_code, error_body)
        raise httpx.HTTPStatusError(f"API error {resp.status_code}: {error_body}", request=resp.request, response=resp)

    def _on_retry(self, attempt: int, exc: Exception):
        logger.warning("[Twilio WhatsApp] Retry %d after: %s", attempt, exc)

    async def download_media(self, media_id: str, mime_type: str) -> bytes | None:
        if not self._http:
            return None
        try:
            url = f"{TWILIO_API_BASE}/Accounts/{self._account_sid}/Messages/{media_id}/Media.json"
            auth = (self._account_sid, self._auth_token)
            resp, attempts = await self._retry.execute(
                self._http.get, url, auth=auth
            )
            resp.raise_for_status()
            data = resp.json()
            media_list = data.get("media_list", [])
            if not media_list:
                return None
            media_uri = media_list[0].get("uri", "")
            if not media_uri:
                return None
            media_url = f"https://api.twilio.com{media_uri}"
            download_resp = await self._http.get(media_url, auth=auth)
            download_resp.raise_for_status()
            return download_resp.content
        except Exception as e:
            logger.error("[Twilio WhatsApp] Media download failed: %s", e)
            return None

    async def health_check(self) -> bool:
        if not self._account_sid or not self._auth_token:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                url = f"{TWILIO_API_BASE}/Accounts/{self._account_sid}.json"
                resp = await client.get(url, auth=(self._account_sid, self._auth_token))
                return resp.status_code == 200
        except Exception:
            return False

    async def get_business_profile(self) -> dict[str, Any]:
        return {"display_phone_number": self._from_number}
