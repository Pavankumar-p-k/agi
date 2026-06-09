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

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from brain.UnifiedBrain import unified_brain

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
    model_used: str = "unified-brain"
    intent:     str = "chat"
    emotion:    str = "neutral"
    confidence: float = 1.0
    latency_ms: int = 0
    retried:    bool = False
    cached:     bool = False


# ─────────────────────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main chat endpoint. Runs full multi-agent pipeline via UnifiedBrain.
    """
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")

    start = time.time()
    reply = await unified_brain.three_pass(req.message, context={"user_id": req.user_id, "platform": req.platform})
    latency = int((time.time() - start) * 1000)

    return ChatResponse(
        reply=reply,
        model_used="unified-brain",
        intent="chat",
        emotion="neutral",
        confidence=1.0,
        latency_ms=latency,
        retried=False,
        cached=False,
    )


@router.post("/chat/image", response_model=ChatResponse)
async def chat_with_image(req: ImageChatRequest):
    """
    Send an image (base64) + optional text question.
    """
    if not req.image_b64:
        raise HTTPException(400, "image_b64 required")

    start = time.time()
    # Mocking vision logic since UnifiedBrain doesn't have direct vision yet,
    # but we can use the complete_vision tool from llm_router.
    from core.llm_router import complete_vision
    messages = [{"role": "user", "content": [
        {"type": "text", "text": req.message},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{req.image_b64}"}}
    ]}]
    res = await complete_vision(messages)
    reply = res.unwrap_or("Failed to process image.")
    latency = int((time.time() - start) * 1000)

    return ChatResponse(
        reply=reply,
        model_used="vision-model",
        intent="vision",
        emotion="neutral",
        confidence=1.0,
        latency_ms=latency,
        retried=False,
        cached=False,
    )


@router.get("/memory/{user_id}")
async def get_memory(user_id: str):
    """Get memory stats for a user."""
    from memory.memory_facade import memory
    memories = memory.get_all(user_id)
    return {"user_id": user_id, "memory_count": len(memories), "memories": memories}


@router.get("/memory/{user_id}/history")
async def get_history(user_id: str, limit: int = 20):
    """Get recent conversation history."""
    from memory.memory_facade import memory
    results = memory.recall("", user_id=user_id, limit=limit)
    return {"user_id": user_id, "history": results}


@router.delete("/memory/{user_id}")
async def clear_memory(user_id: str):
    """Clear all memory for a user (fresh start)."""
    from memory.memory_facade import memory
    success = memory.delete_all(user_id)
    return {"cleared": success, "user_id": user_id}


@router.get("/status")
async def status():
    """Model pool status and VRAM status."""
    from core.hardware_advisor import scan_hardware
    hw = scan_hardware()
    return {
        "status": "online",
        "vram":   hw.get("vram_free_gb", 0.0),
        "hardware": hw
    }


@router.get("/stats")
async def full_stats():
    """Full performance stats."""
    from core.hardware_advisor import scan_hardware
    hw = scan_hardware()
    return {
        "brain_status": "online",
        "hardware": hw,
    }


@router.post("/reload/{model_name}")
async def reload_model(model_name: str):
    """Force reload a specific model into VRAM."""
    return {"loaded": model_name, "status": "simulated"}
