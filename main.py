from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.agi_routes import router as agi_router
from core.agi_core import get_agi


class ChatRequest(BaseModel):
    message: str
    user_id: str = "pavan"


def _detect_intent(text: str) -> str:
    t = text.lower()
    if "remind" in t or "alarm" in t:
        return "reminder"
    if "music" in t or "song" in t or "play" in t:
        return "music"
    if "note" in t:
        return "notes"
    if "plan" in t or "schedule" in t:
        return "planning"
    if "code" in t or "bug" in t or "build" in t:
        return "code"
    if "hello" in t or "hi " in t or t == "hi":
        return "greeting"
    return "small_talk"


def _detect_emotion(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("stressed", "anxious", "worried", "panic")):
        return "anxious"
    if any(k in t for k in ("angry", "mad", "annoyed")):
        return "angry"
    if any(k in t for k in ("sad", "upset", "down")):
        return "sad"
    if any(k in t for k in ("frustrated", "stuck")):
        return "frustrated"
    if any(k in t for k in ("happy", "great", "awesome")):
        return "happy"
    return "neutral"


app = FastAPI(title="JARVIS AGI Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(agi_router)


@app.on_event("startup")
async def _startup() -> None:
    await get_agi().start()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await get_agi().stop()


@app.get("/health")
async def health() -> dict:
    agi = get_agi()
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "agi_running": agi.get_status().get("running", False),
    }


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict:
    agi = get_agi()
    text = req.message.strip()
    intent = _detect_intent(text)
    emotion = _detect_emotion(text)

    # Teach AGI from every interaction (non-blocking).
    asyncio.create_task(agi.on_user_input(text, intent, emotion, user_id=req.user_id))

    # Keep response deterministic in this AGI-only service.
    response = f"I heard: {text}"
    return {
        "response": response,
        "intent": intent,
        "emotion": emotion,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

