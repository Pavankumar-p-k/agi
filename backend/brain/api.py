from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from brain.orchestrator import get_brain
from brain.types import Message
from core.auth import verify_token
from core.database import User

router = APIRouter(prefix="/api/brain", tags=["brain"])


class BrainChatRequest(BaseModel):
    message: str
    user_id: str = ""
    platform: str = "chat"
    session: str = ""


class BrainImageChatRequest(BaseModel):
    message: str = "Describe this image."
    image_b64: str
    user_id: str = ""
    platform: str = "chat"
    session: str = ""


@router.post("/chat")
async def chat(req: BrainChatRequest, user: User = Depends(verify_token)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    brain = get_brain()
    result = await brain.think(
        Message(
            text=req.message,
            user_id=req.user_id or str(user.id),
            platform=req.platform,
            session=req.session,
        )
    )
    return {
        "reply": result.reply,
        "model_used": result.model_used,
        "intent": result.intent,
        "emotion": result.emotion,
        "confidence": result.confidence,
        "latency_ms": result.latency_ms,
        "retried": result.retried,
        "cached": result.cached,
    }


@router.post("/chat/image")
async def chat_image(req: BrainImageChatRequest, user: User = Depends(verify_token)):
    if not req.image_b64:
        raise HTTPException(status_code=400, detail="image_b64 is required.")
    brain = get_brain()
    result = await brain.think(
        Message(
            text=req.message,
            image_b64=req.image_b64,
            user_id=req.user_id or str(user.id),
            platform=req.platform,
            session=req.session,
        )
    )
    return {
        "reply": result.reply,
        "model_used": result.model_used,
        "intent": result.intent,
        "emotion": result.emotion,
        "confidence": result.confidence,
        "latency_ms": result.latency_ms,
        "retried": result.retried,
        "cached": result.cached,
    }


@router.get("/memory/{user_id}")
async def get_memory(user_id: str, _: User = Depends(verify_token)):
    brain = get_brain()
    return await brain.get_memory_stats(user_id)


@router.get("/memory/{user_id}/history")
async def get_history(user_id: str, limit: int = 20, _: User = Depends(verify_token)):
    brain = get_brain()
    recent = await brain.memory.get_recent(user_id, n=max(1, min(limit, 100)))
    return [
        {
            "role": item.role,
            "content": item.content,
            "intent": item.intent,
            "emotion": item.emotion,
            "model": item.model,
            "timestamp": item.timestamp,
        }
        for item in recent
    ]


@router.delete("/memory/{user_id}")
async def clear_memory(user_id: str, _: User = Depends(verify_token)):
    brain = get_brain()
    await brain.clear_memory(user_id)
    return {"cleared": True, "user_id": user_id}


@router.get("/status")
async def status():
    brain = get_brain()
    return {
        "status": "online",
        "vram": brain.pool.vram_status(),
        "models": brain.pool.get_stats(),
    }
