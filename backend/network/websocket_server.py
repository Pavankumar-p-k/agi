from __future__ import annotations

import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[tuple[str, int], WebSocket] = {}
        self.user_devices = defaultdict(set)

    async def connect(self, ws: WebSocket, device_id: str, user_id: int) -> None:
        await ws.accept()
        key = (device_id, user_id)
        self.connections[key] = ws
        self.user_devices[user_id].add(device_id)

    def disconnect(self, device_id: str, user_id: int) -> None:
        key = (device_id, user_id)
        self.connections.pop(key, None)
        if user_id in self.user_devices:
            self.user_devices[user_id].discard(device_id)
            if not self.user_devices[user_id]:
                del self.user_devices[user_id]


connection_manager = ConnectionManager()


async def handle_message(ws: WebSocket, device_id: str, user_id: int, raw: str) -> None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        await ws.send_json({'type': 'error', 'payload': {'message': 'Invalid JSON'}})
        return

    msg_type = payload.get('type', 'unknown')
    body = payload.get('payload', {})

    if msg_type == 'ping':
        await ws.send_json({'type': 'pong', 'payload': {'device_id': device_id, 'user_id': user_id}})
        return

    await ws.send_json(
        {
            'type': 'ack',
            'payload': {
                'device_id': device_id,
                'user_id': user_id,
                'received_type': msg_type,
                'received_payload': body,
            },
        }
    )
