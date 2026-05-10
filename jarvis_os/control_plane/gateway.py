"""Local multi-channel gateway for CLI, desktop, and messaging."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class LocalGateway:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._channels: Dict[str, Dict[str, Any]] = {
            "cli": {"enabled": True, "kind": "local", "status": "ready"},
            "desktop": {"enabled": True, "kind": "local", "status": "ready"},
            "whatsapp": {"enabled": True, "kind": "web", "status": "available"},
            "instagram": {"enabled": True, "kind": "web", "status": "available"},
            "telegram": {"enabled": False, "kind": "bot", "status": "stub"},
            "discord": {"enabled": False, "kind": "bot", "status": "stub"},
            "slack": {"enabled": False, "kind": "bot", "status": "stub"},
        }
        self._messages: List[Dict[str, Any]] = []

    async def initialize(self):
        return None

    async def shutdown(self):
        return None

    def channels(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._channels)

    def record_message(self, channel: str, direction: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        self._messages.append(
            {
                "ts": time.time(),
                "channel": channel,
                "direction": direction,
                "content": content[:500],
                "metadata": metadata or {},
            }
        )
        self._messages = self._messages[-200:]

    def status(self) -> Dict[str, Any]:
        return {
            "channels": self.channels(),
            "recent_messages": self._messages[-20:],
        }
