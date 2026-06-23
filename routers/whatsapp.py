"""routers/whatsapp.py
Meta Cloud API WhatsApp webhook — receive messages, process media, reply via JARVIS.
Uses integrations.whatsapp for provider abstraction and webhook handling.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from core.schemas import ChatRequest
from routers.chat import chat_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")
_webhook_handler = None
_media_manager = None
_cloud_provider = None


async def _get_webhook_handler():
    global _webhook_handler, _media_manager, _cloud_provider
    if _webhook_handler is None:
        from integrations.whatsapp.webhook import WhatsAppWebhookHandler
        from integrations.whatsapp.media import MediaManager
        from integrations.whatsapp.cloud_api import WhatsAppCloudAPIProvider
        _webhook_handler = WhatsAppWebhookHandler()
        _media_manager = MediaManager()
        _cloud_provider = WhatsAppCloudAPIProvider()
        await _cloud_provider.connect()
    return _webhook_handler, _media_manager, _cloud_provider


@router.get("/webhook")
async def verify_webhook(request: Request):
    """Meta sends a GET to verify your webhook endpoint."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if not VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Webhook verification not configured")
    handler, _, _ = await _get_webhook_handler()
    result = handler.verify_webhook_token(mode or "", token or "", challenge or "")
    if result:
        return PlainTextResponse(result)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def incoming_message(request: Request):
    """Receive WhatsApp message with signature verification and media support."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    handler, media_mgr, cloud_provider = await _get_webhook_handler()

    if not handler.verify_signature(body, signature):
        logger.warning("[WHATSAPP] Webhook signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid signature")

    import json
    payload = json.loads(body)

    business_phone = ""
    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])
        if changes:
            value = changes[0].get("value", {})
            business_phone = value.get("metadata", {}).get("display_phone_number", "")
    except (IndexError, KeyError, AttributeError):
        pass

    messages = handler.process_incoming(payload, business_phone)
    for msg in messages:
        try:
            if handler.requires_media_download(msg) and msg.media:
                path = await media_mgr.download_and_cache(cloud_provider, msg.media)
                if path:
                    logger.info("[WHATSAPP] Downloaded media: %s", path)

            if msg.text:
                req = ChatRequest(
                    message=msg.text,
                    platform="whatsapp",
                    user_id=msg.from_number,
                )
                result = await chat_handler(req, endpoint="/api/whatsapp")
                reply = result.get("response", "")
                if reply:
                    kwargs = {}
                    if msg.context_message_id:
                        kwargs["context_message_id"] = msg.id
                    await cloud_provider.send_text(msg.from_number, reply, **kwargs)
                    await cloud_provider.mark_as_read(msg.id)
        except Exception as e:
            logger.warning("[WHATSAPP] Message processing error: %s", e)

    if "entry" not in payload:
        statuses = payload.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("statuses", [])
        if statuses:
            logger.info("[WHATSAPP] Status update: %d statuses", len(statuses))

    return {"status": "ok"}
