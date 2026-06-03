# network/websocket_server.py
from __future__ import annotations

import json
import logging
from typing import Dict

logger = logging.getLogger(__name__)

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, device_id: str, user_id: int) -> None:
        await websocket.accept()
        self.active[f"{device_id}:{user_id}"] = websocket

    def disconnect(self, device_id: str, user_id: int) -> None:
        self.active.pop(f"{device_id}:{user_id}", None)

    async def send(self, websocket: WebSocket, payload: dict) -> None:
        await websocket.send_json(payload)

    async def broadcast(self, payload: dict) -> None:
        disconnected = []
        for key, ws in self.active.items():
            try:
                await ws.send_json(payload)
            except Exception:
                disconnected.append(key)
        for key in disconnected:
            self.active.pop(key, None)


connection_manager = ConnectionManager()


async def handle_message(ws: WebSocket, device_id: str, user_id: int, raw: str) -> None:
    try:
        msg = json.loads(raw)
    except Exception as e:
        logger.exception("[WS] invalid JSON: %s", e)
        await ws.send_json({"type": "error", "payload": {"error": "invalid_json"}})
        return

    msg_type = msg.get("type")
    payload = msg.get("payload", {})

    if msg_type == "ping":
        await ws.send_json({"type": "pong", "payload": {}})
        return

    if msg_type == "chat":
        text = payload.get("text", "")
        if not text:
            await ws.send_json({"type": "chat_response", "payload": {"response": ""}})
            return
        try:
            from core.intent_router import extract_intent
            from core.main import execute_action
            from core.llm_router import get_router
            intent_data = await extract_intent(text)
            intent = intent_data.get("intent", "chat")
            action_result = await execute_action(intent_data, message=text)
            resp = await get_router().acompletion(
                model=intent,
                messages=[{"role": "user", "content": text}],
                timeout=30,
            )
            response = resp.choices[0].message.content or ""
            if action_result.get("executed") and not action_result.get("error"):
                response += f"\n{action_result.get('action', '')}"
            await ws.send_json({"type": "chat_response", "payload": {
                "intent": intent, "response": response, "user_text": text,
            }})
        except Exception as e:
            logger.exception("[WS] chat handler failed")
            await ws.send_json({"type": "chat_response", "payload": {"response": str(e)}})
        return

    await ws.send_json({"type": "echo", "payload": payload})
