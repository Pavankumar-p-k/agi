from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


class MessageSendRequest(BaseModel):
    contact: str
    text: str
    platform: str = "auto"


class CallAnswerRequest(BaseModel):
    caller: str = ""
    script: str


class TTSRequest(BaseModel):
    text: str


class IncomingMessageRequest(BaseModel):
    contact: str
    text: str
    platform: str = "auto"
    unread_increment: int = 1


app = FastAPI(title="JARVIS Device Companion", version="1.0.0")

COMPANION_MODE = os.getenv("COMPANION_MODE", "termux").strip().lower()  # termux | mock
BRIDGE_TOKEN = os.getenv("JARVIS_BRIDGE_TOKEN", "").strip()
CALL_ANSWER_COMMAND = os.getenv("COMPANION_CALL_ANSWER_COMMAND", "").strip()
BUSY_SMS_TEMPLATE = os.getenv(
    "COMPANION_BUSY_SMS_TEMPLATE",
    "Sir is busy right now. You can leave a note or reminder.",
).strip()
AUTO_BUSY_SMS_ON_CALL_FAIL = os.getenv("COMPANION_AUTO_BUSY_SMS_ON_CALL_FAIL", "1").strip() == "1"

_unread_messages = 0
_inbox: list[dict[str, Any]] = []
_sent_messages: list[dict[str, Any]] = []


def _require_token(x_bridge_token: str | None) -> None:
    if BRIDGE_TOKEN and x_bridge_token != BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bridge token")


async def _run_cmd(args: list[str]) -> tuple[bool, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out_b, err_b = await proc.communicate()
        out = (out_b or b"").decode(errors="ignore").strip()
        err = (err_b or b"").decode(errors="ignore").strip()
        if proc.returncode == 0:
            return True, out or "ok"
        return False, err or out or f"exit_{proc.returncode}"
    except Exception as exc:
        return False, str(exc)


async def _run_shell(command: str) -> tuple[bool, str]:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out_b, err_b = await proc.communicate()
        out = (out_b or b"").decode(errors="ignore").strip()
        err = (err_b or b"").decode(errors="ignore").strip()
        if proc.returncode == 0:
            return True, out or "ok"
        return False, err or out or f"exit_{proc.returncode}"
    except Exception as exc:
        return False, str(exc)


async def _termux_tts(text: str) -> tuple[bool, str]:
    return await _run_cmd(["termux-tts-speak", text])


async def _termux_sms(contact: str, text: str) -> tuple[bool, str]:
    return await _run_cmd(["termux-sms-send", "-n", contact, text])


async def _termux_answer_call_and_tts(caller: str, script: str) -> dict[str, Any]:
    if CALL_ANSWER_COMMAND:
        safe_caller = caller.replace('"', "'")
        safe_script = script.replace('"', "'")
        cmd = CALL_ANSWER_COMMAND.format(caller=safe_caller, script=safe_script)
        ok, out = await _run_shell(cmd)
        if ok:
            return {"success": True, "mode": "termux", "output": out, "strategy": "custom_command"}
        return {"success": False, "mode": "termux", "error": out, "strategy": "custom_command"}

    # Fallback attempt: headset hook to answer, then speak.
    ok_a, out_a = await _run_shell("input keyevent KEYCODE_HEADSETHOOK")
    ok_t, out_t = await _termux_tts(script)
    if ok_a and ok_t:
        return {"success": True, "mode": "termux", "strategy": "headsethook+tts", "output": out_t}

    if AUTO_BUSY_SMS_ON_CALL_FAIL and caller:
        await _termux_sms(caller, BUSY_SMS_TEMPLATE)

    return {
        "success": False,
        "mode": "termux",
        "error": f"answer={out_a}; tts={out_t}",
        "strategy": "fallback_failed",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "mode": COMPANION_MODE,
        "token_required": bool(BRIDGE_TOKEN),
    }


@app.get("/bridge/config")
async def bridge_config(x_bridge_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_bridge_token)
    return {
        "mode": COMPANION_MODE,
        "token_required": bool(BRIDGE_TOKEN),
        "call_answer_command_configured": bool(CALL_ANSWER_COMMAND),
        "auto_busy_sms_on_call_fail": AUTO_BUSY_SMS_ON_CALL_FAIL,
        "unread_messages": _unread_messages,
    }


@app.post("/bridge/messages/send")
async def bridge_messages_send(req: MessageSendRequest, x_bridge_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_bridge_token)
    contact = req.contact.strip()
    text = req.text.strip()
    if not contact or not text:
        return {"success": False, "error": "missing_contact_or_text"}

    if COMPANION_MODE == "mock":
        payload = {"success": True, "mode": "mock", "contact": contact}
    else:
        ok, out = await _termux_sms(contact, text)
        payload = {"success": ok, "mode": "termux", "output": out} if ok else {"success": False, "mode": "termux", "error": out}

    _sent_messages.append(
        {
            "contact": contact,
            "text": text,
            "platform": req.platform,
            "timestamp": datetime.utcnow().isoformat(),
            "success": bool(payload.get("success")),
        }
    )
    return payload


@app.post("/bridge/calls/answer_tts")
async def bridge_calls_answer_tts(req: CallAnswerRequest, x_bridge_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_bridge_token)
    caller = req.caller.strip()
    script = req.script.strip()
    if not script:
        return {"success": False, "error": "missing_script"}

    if COMPANION_MODE == "mock":
        return {"success": True, "mode": "mock", "caller": caller}
    return await _termux_answer_call_and_tts(caller=caller, script=script)


@app.post("/bridge/tts")
async def bridge_tts(req: TTSRequest, x_bridge_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_bridge_token)
    text = req.text.strip()
    if not text:
        return {"success": False, "error": "missing_text"}

    if COMPANION_MODE == "mock":
        return {"success": True, "mode": "mock"}
    ok, out = await _termux_tts(text)
    return {"success": ok, "mode": "termux", "output": out} if ok else {"success": False, "mode": "termux", "error": out}


@app.post("/bridge/messages/incoming")
async def bridge_messages_incoming(req: IncomingMessageRequest, x_bridge_token: str | None = Header(default=None)) -> dict[str, Any]:
    global _unread_messages
    _require_token(x_bridge_token)
    item = {
        "contact": req.contact.strip(),
        "text": req.text.strip(),
        "platform": req.platform,
        "timestamp": datetime.utcnow().isoformat(),
    }
    _inbox.append(item)
    _unread_messages += max(0, int(req.unread_increment))
    return {"success": True, "unread_messages": _unread_messages}


@app.post("/bridge/messages/mark_read")
async def bridge_messages_mark_read(x_bridge_token: str | None = Header(default=None)) -> dict[str, Any]:
    global _unread_messages
    _require_token(x_bridge_token)
    _unread_messages = 0
    return {"success": True, "unread_messages": _unread_messages}


@app.get("/bridge/messages/unread_count")
async def bridge_messages_unread_count(x_bridge_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_bridge_token)
    return {"count": _unread_messages}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("device_companion:app", host="0.0.0.0", port=8090, reload=False)
