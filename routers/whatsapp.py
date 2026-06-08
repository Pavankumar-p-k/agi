"""routers/whatsapp.py
Meta Cloud API WhatsApp webhook — receive messages, reply via JARVIS.
Setup:
  1. Meta Developer account → WhatsApp Business API sandbox
  2. Set META_WHATSAPP_TOKEN, META_WHATSAPP_PHONE_ID in .env
  3. Set webhook URL to https://your-domain/api/whatsapp/webhook
  4. Verify token (below) must match what you enter in Meta dashboard
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from core.schemas import ChatRequest
from routers.chat import chat_handler
from tools.whatsapp_sender import whatsapp_sender

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
if not VERIFY_TOKEN:
    raise ValueError("META_VERIFY_TOKEN environment variable is required")


@router.get("/webhook")
async def verify_webhook(request: Request):
    """Meta sends a GET to verify your webhook endpoint."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("[WHATSAPP] Webhook verified")
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def incoming_message(request: Request):
    """Receive WhatsApp message → JARVIS chat_handler → reply via Meta API."""
    body = await request.json()
    try:
        entry = body["entry"][0]
        change = entry["changes"][0]["value"]
        if "messages" not in change:
            return {"status": "ok"}
        msg = change["messages"][0]
        if msg.get("type") != "text":
            logger.debug("[WHATSAPP] Skipped non-text message: %s", msg.get("type", "unknown"))
            return {"status": "ok"}
        sender = msg["from"]
        text = msg["text"]["body"]
        logger.info("[WHATSAPP] From %s: %.80s", sender, text)
        req = ChatRequest(
            message=text,
            platform="mobile",
        )
        result = await chat_handler(req, endpoint="/api/whatsapp")
        reply = result.get("response", "Sorry, I couldn't process that.")
        await whatsapp_sender.send(sender, reply)
    except Exception as e:
        logger.warning("[WHATSAPP] Webhook error: %s", e)
    return {"status": "ok"}
