# network/websocket_server.py
from __future__ import annotations

import json
from typing import Dict

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


connection_manager = ConnectionManager()


async def handle_message(ws: WebSocket, device_id: str, user_id: int, raw: str) -> None:
    try:
        msg = json.loads(raw)
    except Exception:
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
            from assistant.engine import jarvis
            result = await jarvis.process_text(text, user_id=user_id)
            await ws.send_json({"type": "chat_response", "payload": result})
        except Exception as e:
            await ws.send_json({"type": "chat_response", "payload": {"response": str(e)}})
        return

    await ws.send_json({"type": "echo", "payload": payload})
