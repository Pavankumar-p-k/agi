from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import httpx


class JarvisTools:
    """
    Async bridge between AGI layer and JARVIS API endpoints.
    """

    def __init__(self):
        self.base_url = os.getenv("JARVIS_API", "http://localhost:8000").rstrip("/")

    async def _get(self, path: str, timeout: float = 12.0) -> tuple[bool, Any]:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.get(f"{self.base_url}{path}")
                if res.status_code >= 400:
                    return False, {"error": res.text, "status": res.status_code}
                return True, res.json()
        except Exception as exc:
            return False, {"error": str(exc)}

    async def _post(self, path: str, payload: dict[str, Any], timeout: float = 20.0) -> tuple[bool, Any]:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(f"{self.base_url}{path}", json=payload)
                if res.status_code >= 400:
                    return False, {"error": res.text, "status": res.status_code}
                if res.text.strip():
                    return True, res.json()
                return True, {}
        except Exception as exc:
            return False, {"error": str(exc)}

    async def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        ok, _ = await self._post("/api/tts", {"text": text})
        if not ok:
            # Fallback: no exception noise in autonomous loop.
            print(f"[JarvisTools] speak fallback: {text}")

    async def ask_brain(self, query: str, user_id: str = "pavan") -> str:
        query = (query or "").strip()
        if not query:
            return ""
        ok, data = await self._post("/api/brain/chat", {"message": query, "user_id": user_id}, timeout=60.0)
        if ok and isinstance(data, dict):
            return str(data.get("reply", "")).strip()

        ok2, data2 = await self._post("/api/chat", {"message": query}, timeout=60.0)
        if ok2 and isinstance(data2, dict):
            return str(data2.get("response", "")).strip()
        return ""

    async def play_music(self, mode: str = "random") -> dict[str, Any]:
        ok, data = await self._post("/api/media/play", {"mode": mode})
        return data if ok and isinstance(data, dict) else {}

    async def list_reminders(self) -> list[dict[str, Any]]:
        ok, data = await self._get("/api/reminders")
        if not ok:
            return []
        if isinstance(data, list):
            return [dict(item) for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and isinstance(data.get("reminders"), list):
            return [dict(item) for item in data["reminders"] if isinstance(item, dict)]
        return []

    async def count_pending_reminders(self) -> int:
        reminders = await self.list_reminders()
        pending = 0
        for reminder in reminders:
            if reminder.get("done") is True:
                continue
            if reminder.get("is_done") is True:
                continue
            pending += 1
        return pending

    async def count_unread_messages(self) -> int:
        ok, data = await self._get("/api/messages/unread_count")
        if ok and isinstance(data, dict):
            try:
                return int(data.get("count", 0))
            except Exception:
                return 0
        return 0

    async def create_reminder(self, title: str, time_str: str = "") -> bool:
        title = (title or "").strip()
        if not title:
            return False
        remind_at = (time_str or "").strip()
        if not remind_at:
            remind_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        payload = {
            "title": title,
            "remind_at": remind_at,
            "description": "",
            "repeat": "none",
        }
        ok, _ = await self._post("/api/reminders", payload)
        return ok

    async def list_recent_notes(self) -> list[dict[str, Any]]:
        ok, data = await self._get("/api/notes")
        if not ok:
            return []
        if isinstance(data, list):
            return [dict(item) for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and isinstance(data.get("notes"), list):
            return [dict(item) for item in data["notes"] if isinstance(item, dict)]
        return []

    async def open_url(self, url: str) -> bool:
        url = (url or "").strip()
        if not url:
            return False
        ok, _ = await self._post("/api/automation/browser/open", {"url": url})
        return ok

    async def send_message(self, contact: str, text: str, platform: str = "auto") -> bool:
        payload = {
            "contact": (contact or "").strip(),
            "text": (text or "").strip(),
            "platform": (platform or "auto").strip(),
        }
        if not payload["contact"] or not payload["text"]:
            return False
        ok, _ = await self._post("/api/messages/send", payload)
        if not ok:
            print(f"[JarvisTools] send_message fallback -> {payload}")
        return ok

    async def answer_call_with_tts(self, caller: str, script: str) -> bool:
        payload = {
            "caller": (caller or "").strip(),
            "script": (script or "").strip(),
        }
        if not payload["script"]:
            return False
        ok, _ = await self._post("/api/calls/answer_tts", payload)
        if not ok:
            print(f"[JarvisTools] answer_call_with_tts fallback -> {payload}")
        return ok

    async def get_daily_briefing(self) -> str:
        reminders = await self.list_reminders()
        notes = await self.list_recent_notes()
        parts = ["Good morning. Here is your JARVIS briefing."]
        if reminders:
            parts.append(f"You have {len(reminders)} reminders.")
        if notes:
            parts.append(f"You have {len(notes)} recent notes.")
        if not reminders and not notes:
            parts.append("No urgent items detected.")
        return " ".join(parts)

    async def get_daily_summary(self) -> str:
        ok, data = await self._get("/api/activity/summary", timeout=20.0)
        if ok and isinstance(data, dict):
            text = str(data.get("summary", "")).strip()
            if text:
                return text
        return "Daily summary is unavailable right now."

    async def get_task_list(self) -> list[dict[str, Any]]:
        reminders = await self.list_reminders()
        return [
            r for r in reminders
            if not r.get("is_done") and not r.get("done")
        ]

    async def call(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        ok, data = await self._post(f"/api/tools/{tool_name}", params)
        return data if ok and isinstance(data, dict) else {"success": False}
