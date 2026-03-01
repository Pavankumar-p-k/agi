from __future__ import annotations

import asyncio
import itertools
import webbrowser
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from android_bridge import AndroidBridge
from api.agi_routes import router as agi_router
from core.agi_core import get_agi


class ChatRequest(BaseModel):
    message: str
    user_id: str = "pavan"


class TTSRequest(BaseModel):
    text: str


class MessageSendRequest(BaseModel):
    contact: str
    text: str
    platform: str = "auto"


class MessageIncomingRequest(BaseModel):
    contact: str
    text: str
    platform: str = "auto"
    unread_increment: int = 1


class ReminderCreateRequest(BaseModel):
    title: str
    remind_at: str = ""
    description: str = ""
    repeat: str = "none"


class NoteCreateRequest(BaseModel):
    title: str
    content: str = ""


class BrainChatRequest(BaseModel):
    message: str
    user_id: str = "pavan"


class CallAnswerRequest(BaseModel):
    caller: str = ""
    script: str


class BrowserOpenRequest(BaseModel):
    url: str


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


app = FastAPI(title="JARVIS AGI Service", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(agi_router)

_bridge = AndroidBridge()
_id_counter = itertools.count(1)
_reminders: list[dict[str, Any]] = []
_notes: list[dict[str, Any]] = []
_inbox: list[dict[str, Any]] = []
_sent_messages: list[dict[str, Any]] = []
_unread_messages = 0


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
        "bridge": _bridge.config(),
    }


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict:
    agi = get_agi()
    text = req.message.strip()
    intent = _detect_intent(text)
    emotion = _detect_emotion(text)

    asyncio.create_task(agi.on_user_input(text, intent, emotion, user_id=req.user_id))

    response = f"I heard: {text}"
    return {
        "response": response,
        "intent": intent,
        "emotion": emotion,
    }


@app.post("/api/brain/chat")
async def brain_chat(req: BrainChatRequest) -> dict:
    agi = get_agi()
    text = req.message.strip()
    intent = _detect_intent(text)
    emotion = _detect_emotion(text)

    asyncio.create_task(agi.on_user_input(text, intent, emotion, user_id=req.user_id))
    styled = await agi.build_styled_reply(
        incoming_text=text,
        intent=intent,
        user_id=req.user_id,
        auto_send=False,
    )
    return {
        "reply": styled.get("reply", ""),
        "intent": intent,
        "emotion": emotion,
    }


@app.post("/api/tts")
async def tts(req: TTSRequest) -> dict:
    text = req.text.strip()
    if not text:
        return {"success": False, "error": "missing_text"}
    print(f"[TTS] {text}")
    return {"success": True}


@app.post("/api/messages/send")
async def messages_send(req: MessageSendRequest) -> dict:
    payload = await _bridge.send_message(contact=req.contact, text=req.text, platform=req.platform)
    payload.setdefault("success", False)

    _sent_messages.append(
        {
            "id": next(_id_counter),
            "contact": req.contact,
            "text": req.text,
            "platform": req.platform,
            "timestamp": datetime.utcnow().isoformat(),
            "success": bool(payload.get("success")),
            "mode": payload.get("mode", ""),
        }
    )
    return payload


@app.post("/api/messages/incoming")
async def messages_incoming(req: MessageIncomingRequest) -> dict:
    global _unread_messages
    event = {
        "id": next(_id_counter),
        "contact": req.contact,
        "text": req.text,
        "platform": req.platform,
        "timestamp": datetime.utcnow().isoformat(),
    }
    _inbox.append(event)
    _unread_messages += max(0, int(req.unread_increment))
    return {"success": True, "unread": _unread_messages}


@app.post("/api/messages/mark_read")
async def messages_mark_read() -> dict:
    global _unread_messages
    _unread_messages = 0
    return {"success": True, "unread": _unread_messages}


@app.get("/api/messages/unread_count")
async def messages_unread_count() -> dict:
    return {"count": int(_unread_messages)}


@app.post("/api/calls/answer_tts")
async def calls_answer_tts(req: CallAnswerRequest) -> dict:
    return await _bridge.answer_call_with_tts(caller=req.caller, script=req.script)


@app.get("/api/reminders")
async def reminders_list() -> list[dict[str, Any]]:
    return list(_reminders)


@app.post("/api/reminders")
async def reminders_create(req: ReminderCreateRequest) -> dict:
    item = {
        "id": next(_id_counter),
        "title": req.title.strip(),
        "remind_at": req.remind_at.strip(),
        "description": req.description.strip(),
        "repeat": req.repeat.strip(),
        "done": False,
        "created_at": datetime.utcnow().isoformat(),
    }
    if not item["title"]:
        return {"success": False, "error": "missing_title"}
    _reminders.append(item)
    return {"success": True, **item}


@app.get("/api/notes")
async def notes_list() -> list[dict[str, Any]]:
    return list(_notes)


@app.post("/api/notes")
async def notes_create(req: NoteCreateRequest) -> dict:
    note = {
        "id": next(_id_counter),
        "title": req.title.strip() or "Untitled",
        "content": req.content.strip(),
        "created_at": datetime.utcnow().isoformat(),
    }
    _notes.append(note)
    return {"success": True, **note}


@app.get("/api/activity/summary")
async def activity_summary() -> dict:
    return {
        "summary": (
            f"Messages sent: {len(_sent_messages)}. "
            f"Unread messages: {_unread_messages}. "
            f"Notes: {len(_notes)}. "
            f"Reminders: {len(_reminders)}."
        )
    }


@app.post("/api/media/play")
async def media_play(payload: dict[str, Any]) -> dict:
    mode = str(payload.get("mode", "random"))
    return {"success": True, "message": f"Media play requested ({mode})"}


@app.post("/api/automation/browser/open")
async def browser_open(req: BrowserOpenRequest) -> dict:
    url = req.url.strip()
    if not url:
        return {"success": False, "error": "missing_url"}
    webbrowser.open(url)
    return {"success": True, "url": url}


@app.post("/api/tools/{tool_name}")
async def generic_tool_call(tool_name: str, payload: dict[str, Any]) -> dict:
    return {
        "success": False,
        "tool": tool_name,
        "message": "No generic tool handler configured",
        "payload": payload,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
