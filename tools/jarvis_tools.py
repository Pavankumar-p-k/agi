# tools/jarvis_tools.py
from __future__ import annotations

from typing import Any

from core.config import DEV_MODE


class JarvisTools:
    def __init__(self) -> None:
        self.dev_mode = DEV_MODE
        self.initialized_at = 0.0

    async def count_pending_reminders(self) -> int:
        # Placeholder; integrate with reminders DB in production
        return 0

    async def count_unread_messages(self) -> int:
        return 0

    async def speak(self, text: str) -> dict:
        if DEV_MODE:
            print(f"[JARVIS][Speak] {text}")
        return {"spoken": text}

    async def list_reminders(self) -> list:
        return []

    async def daily_summary(self) -> dict:
        return {"summary": "No summary available"}

    async def brain(self, message: str) -> dict:
        return {"reply": message}
