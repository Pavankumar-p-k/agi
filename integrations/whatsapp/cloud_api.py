from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx

from .base import BaseWhatsAppProvider
from .models import InteractiveBody, InteractiveButton, InteractiveListRow, InteractiveListSection, MessageType, ProviderType, SendResult, WhatsAppMedia, WhatsAppMessage
from .retry import AsyncRetry

logger = logging.getLogger(__name__)

META_API_BASE = "https://graph.facebook.com/v18.0"
MEDIA_API_BASE = "https://graph.facebook.com/v18.0"


class WhatsAppCloudAPIProvider(BaseWhatsAppProvider):
    name = "whatsapp_cloud_api"

    def __init__(self):
        super().__init__()
        self._token: str = ""
        self._phone_id: str = ""
        self._business_phone: str = ""
        self._http: httpx.AsyncClient | None = None
        self._retry = AsyncRetry(max_attempts=3, base_delay=1.0, retryable_exceptions=(httpx.HTTPError,))
        self._media_dir = Path(tempfile.gettempdir()) / "jarvis_whatsapp_media"

    async def connect(self, **kwargs) -> bool:
        self._token = kwargs.get("token", "") or os.getenv("META_WHATSAPP_TOKEN", "")
        self._phone_id = kwargs.get("phone_id", "") or os.getenv("META_WHATSAPP_PHONE_ID", "")
        if not self._token or not self._phone_id:
            logger.warning("[WhatsApp Cloud API] Missing token or phone_id")
            return False
        self._http = httpx.AsyncClient(timeout=15)
        self._media_dir.mkdir(parents=True, exist_ok=True)
        ok = await self.health_check()
        if ok:
            profile = await self.get_business_profile()
            self._business_phone = profile.get("display_phone_number", "")
            self._connected = True
            logger.info("[WhatsApp Cloud API] Connected — %s", self._business_phone)
        else:
            logger.warning("[WhatsApp Cloud API] Health check failed after connect")
        return ok

    async def disconnect(self) -> bool:
        self._connected = False
        if self._http:
            await self._http.aclose()
            self._http = None
        return True

    async def send_text(self, to: str, text: str, **kwargs) -> SendResult:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": text[:4096]},
        }
        if kwargs.get("preview_url"):
            payload["text"]["preview_url"] = True
        if kwargs.get("context_message_id"):
            payload["context"] = {"message_id": kwargs["context_message_id"]}
        return await self._post(payload)

    async def send_image(self, to: str, image_url: str, caption: str | None = None, **kwargs) -> SendResult:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": {"link": image_url},
        }
        if caption:
            payload["image"]["caption"] = caption[:1024]
        if kwargs.get("context_message_id"):
            payload["context"] = {"message_id": kwargs["context_message_id"]}
        return await self._post(payload)

    async def send_document(self, to: str, document_url: str, filename: str, caption: str | None = None, **kwargs) -> SendResult:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "document",
            "document": {"link": document_url, "filename": filename},
        }
        if caption:
            payload["document"]["caption"] = caption[:1024]
        if kwargs.get("context_message_id"):
            payload["context"] = {"message_id": kwargs["context_message_id"]}
        return await self._post(payload)

    async def send_audio(self, to: str, audio_url: str, **kwargs) -> SendResult:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "audio",
            "audio": {"link": audio_url},
        }
        if kwargs.get("context_message_id"):
            payload["context"] = {"message_id": kwargs["context_message_id"]}
        return await self._post(payload)

    async def send_location(self, to: str, latitude: float, longitude: float, name: str | None = None, address: str | None = None, **kwargs) -> SendResult:
        location = {"latitude": latitude, "longitude": longitude}
        if name:
            location["name"] = name
        if address:
            location["address"] = address
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "location",
            "location": location,
        }
        return await self._post(payload)

    async def _post(self, payload: dict) -> SendResult:
        if not self._http:
            return SendResult(success=False, error="Not connected", provider=self.name)
        try:
            result, attempts = await self._retry.execute(
                self._do_post, payload, on_retry=self._on_retry
            )
            return result
        except Exception as e:
            return SendResult(success=False, error=str(e), retry_attempts=0, provider=self.name)

    async def _do_post(self, payload: dict) -> SendResult:
        url = f"{META_API_BASE}/{self._phone_id}/messages"
        resp = await self._http.post(
            url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if resp.status_code == 200:
            data = resp.json()
            msg_id = data.get("messages", [{}])[0].get("id", "")
            return SendResult(success=True, message_id=msg_id, provider=self.name)
        error_body = resp.text[:500]
        logger.warning("[WhatsApp Cloud API] POST failed: %d %s", resp.status_code, error_body)
        raise httpx.HTTPStatusError(f"API error {resp.status_code}: {error_body}", request=resp.request, response=resp)

    def _on_retry(self, attempt: int, exc: Exception):
        logger.warning("[WhatsApp Cloud API] Retry %d after: %s", attempt, exc)

    async def download_media(self, media_id: str, mime_type: str) -> bytes | None:
        if not self._http:
            return None
        try:
            url_resp, _ = await self._retry.execute(self._get_media_url, media_id)
            download_url = url_resp.get("url", "")
            if not download_url:
                return None
            data, _ = await self._retry.execute(self._download_url, download_url)
            return data
        except Exception as e:
            logger.error("[WhatsApp Cloud API] Media download failed: %s", e)
            return None

    async def _get_media_url(self, media_id: str) -> dict:
        url = f"{MEDIA_API_BASE}/{media_id}"
        resp = await self._http.get(
            url, headers={"Authorization": f"Bearer {self._token}"}
        )
        resp.raise_for_status()
        return resp.json()

    async def _download_url(self, download_url: str) -> bytes:
        resp = await self._http.get(
            download_url, headers={"Authorization": f"Bearer {self._token}"}
        )
        resp.raise_for_status()
        return resp.content

    async def health_check(self) -> bool:
        if not self._token or not self._phone_id:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                url = f"{META_API_BASE}/{self._phone_id}/message_templates?limit=1"
                resp = await client.get(
                    url, headers={"Authorization": f"Bearer {self._token}"}
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def get_business_profile(self) -> dict[str, Any]:
        if not self._http:
            return {}
        try:
            url = f"{META_API_BASE}/{self._phone_id}/whatsapp_business_profile"
            params = {"fields": "display_phone_number,verified_name,business_details,profile_picture_url"}
            resp = await self._http.get(
                url, headers={"Authorization": f"Bearer {self._token}"}, params=params
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", [{}])[0] if data.get("data") else {}
        except Exception as e:
            logger.warning("[WhatsApp Cloud API] Profile fetch failed: %s", e)
        return {}

    async def send_template(self, to: str, template_name: str, language: str = "en", components: list[dict] | None = None) -> SendResult:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            },
        }
        if components:
            payload["template"]["components"] = components
        return await self._post(payload)

    async def send_interactive_buttons(self, to: str, body: InteractiveBody, **kwargs) -> SendResult:
        if not body.action or not body.action.buttons:
            return SendResult(success=False, error="No buttons provided", provider=self.name)
        buttons = []
        for btn in body.action.buttons:
            buttons.append({"type": "reply", "reply": {"id": btn.id, "title": btn.title[:20]}})
        interactive = {
            "type": "button",
            "body": {"text": body.text[:1024]},
        }
        if body.title:
            interactive["header"] = {"type": "text", "text": body.title[:60]}
        if body.footer:
            interactive["footer"] = {"text": body.footer[:60]}
        interactive["action"] = {"buttons": buttons}
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }
        return await self._post(payload)

    async def send_interactive_list(self, to: str, body: InteractiveBody, **kwargs) -> SendResult:
        if not body.action or not body.action.sections:
            return SendResult(success=False, error="No list sections provided", provider=self.name)
        sections = []
        for sec in body.action.sections:
            rows = []
            for row in sec.rows:
                r: dict = {"id": row.id, "title": row.title[:24]}
                if row.description:
                    r["description"] = row.description[:72]
                rows.append(r)
            sections.append({"title": sec.title[:24], "rows": rows})
        interactive = {
            "type": "list",
            "body": {"text": body.text[:1024]},
            "action": {
                "button": (body.action.button or "Select")[:20],
                "sections": sections,
            },
        }
        if body.title:
            interactive["header"] = {"type": "text", "text": body.title[:60]}
        if body.footer:
            interactive["footer"] = {"text": body.footer[:60]}
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }
        return await self._post(payload)

    async def mark_as_read(self, message_id: str) -> bool:
        if not self._http:
            return False
        try:
            url = f"{META_API_BASE}/{self._phone_id}/messages"
            resp = await self._http.post(
                url,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                json={"messaging_product": "whatsapp", "status": "read", "message_id": message_id},
            )
            return resp.status_code == 200
        except Exception as e:
            logger.warning("[WhatsApp Cloud API] Mark read failed: %s", e)
            return False
