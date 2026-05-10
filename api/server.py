# api/server.py
#
# JARVIS BRAIN API SERVER
# Exposes the multi-agent brain as a FastAPI REST service.
# Drop-in replacement / extension of your existing JARVIS backend.
#
# Endpoints:
#   POST /brain/chat          — main multi-agent chat
#   POST /brain/chat/image    — image + text (uses moondream)
#   GET  /brain/memory/{user} — memory stats + facts
#   DELETE /brain/memory/{user} — clear memory
#   GET  /brain/status        — model pool + VRAM status
#   GET  /brain/stats         — full performance stats
#   POST /brain/reload        — force reload a model
#
# Usage: add these routes to your existing main.py:
#   from api.server import router as brain_router
#   app.include_router(brain_router)

import base64
import time
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from orchestrator.brain import get_brain, Message


router = APIRouter(prefix="/brain", tags=["brain"])


# ─────────────────────────────────────────────────────────────
#  Request / Response models
# ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message:   str
    user_id:   str      = "pavan"
    platform:  str      = "chat"
    session:   str      = ""

class ImageChatRequest(BaseModel):
    message:   str      = "Describe this image"
    image_b64: str      = ""   # base64 encoded image
    user_id:   str      = "pavan"
    platform:  str      = "chat"

class ChatResponse(BaseModel):
    reply:      str
    model_used: str
    intent:     str
    emotion:    str
    confidence: float
    latency_ms: int
    retried:    bool
    cached:     bool


# ─────────────────────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main chat endpoint. Runs full multi-agent pipeline.
    Automatically routes to best model based on message content.
    """
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")

    brain = get_brain()
    msg   = Message(
        text=req.message,
        user_id=req.user_id,
        platform=req.platform,
        session=req.session,
    )
    result = await brain.think(msg)

    return ChatResponse(
        reply=result.reply,
        model_used=result.model_used,
        intent=result.intent,
        emotion=result.emotion,
        confidence=result.confidence,
        latency_ms=result.latency_ms,
        retried=result.retried,
        cached=result.cached,
    )


@router.post("/chat/image", response_model=ChatResponse)
async def chat_with_image(req: ImageChatRequest):
    """
    Send an image (base64) + optional text question.
    Always routes to moondream.
    """
    if not req.image_b64:
        raise HTTPException(400, "image_b64 required")

    brain = get_brain()
    msg   = Message(
        text=req.message,
        image_b64=req.image_b64,
        user_id=req.user_id,
        platform=req.platform,
    )
    result = await brain.think(msg)

    return ChatResponse(
        reply=result.reply, model_used=result.model_used,
        intent=result.intent, emotion=result.emotion,
        confidence=result.confidence, latency_ms=result.latency_ms,
        retried=result.retried, cached=result.cached,
    )


@router.get("/memory/{user_id}")
async def get_memory(user_id: str):
    """Get memory stats, known facts, and emotion trends for a user."""
    brain = get_brain()
    return await brain.get_memory_stats(user_id)


@router.get("/memory/{user_id}/history")
async def get_history(user_id: str, limit: int = 20):
    """Get recent conversation history."""
    brain  = get_brain()
    recent = await brain.memory.get_recent(user_id, limit)
    return [
        {"role": m.role, "content": m.content, "intent": m.intent,
         "emotion": m.emotion, "model": m.model, "timestamp": m.timestamp}
        for m in recent
    ]


@router.delete("/memory/{user_id}")
async def clear_memory(user_id: str):
    """Clear all memory for a user (fresh start)."""
    brain = get_brain()
    await brain.clear_memory(user_id)
    return {"cleared": True, "user_id": user_id}


@router.get("/status")
async def status():
    """Model pool status and VRAM usage."""
    brain = get_brain()
    return {
        "status": "online",
        "vram":   brain.pool.vram_status(),
        "models": brain.pool.get_stats(),
    }


@router.get("/stats")
async def full_stats():
    """Full performance stats across all models and users."""
    brain = get_brain()
    pavan = await brain.get_memory_stats("pavan")
    return {
        "brain_status": "online",
        "models":       brain.pool.get_stats(),
        "vram":         brain.pool.vram_status(),
        "pavan_memory": pavan,
    }


@router.post("/reload/{model_name}")
async def reload_model(model_name: str):
    """Force reload a specific model into VRAM."""
    brain = get_brain()
    await brain.pool._ensure_loaded(model_name)
    return {"loaded": model_name, "vram": brain.pool.vram_status()}


# ─────────────────────────────────────────────────────────────
#  Add to your existing main.py:
#
#  from api.server import router as brain_router
#  from orchestrator.brain import get_brain, Message
#  import asyncio
#
#  app = FastAPI()
#  app.include_router(brain_router)
#
#  @app.on_event("startup")
#  async def on_startup():
#      brain = get_brain()
#      await brain.startup()   # warms up phi3 + mistral
#
#  # Replace your old /api/chat endpoint with:
#  @app.post("/api/chat")
#  async def legacy_chat(body: dict):
#      brain  = get_brain()
#      result = await brain.think(Message(text=body["message"]))
#      return {"response": result.reply, "model": result.model_used}
# ─────────────────────────────────────────────────────────────
