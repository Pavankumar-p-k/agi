# memory/agi_memory.py
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any

from core.config import BASE_DIR


class AGIMemory:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (BASE_DIR / "data" / "agi_memory.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text(json.dumps({"events": [], "goals": [], "decisions": []}, indent=2))

    def _load(self) -> Dict[str, Any]:
        try:
            return json.loads(self._path.read_text())
        except Exception:
            return {"events": [], "goals": [], "decisions": []}

    def _save(self, data: Dict[str, Any]) -> None:
        self._path.write_text(json.dumps(data, indent=2))

    async def save_event(self, event: Dict[str, Any]) -> None:
        data = self._load()
        data["events"].append(event)
        self._save(data)

    async def get_recent_events(self, n: int = 10) -> List[Dict[str, Any]]:
        data = self._load()
        return list(data.get("events", []))[-n:]

    async def get_latest_mood(self) -> str:
        data = self._load()
        for e in reversed(data.get("events", [])):
            if e.get("mood"):
                return e["mood"]
        return "neutral"

    async def save_decision(self, decision: Dict[str, Any]) -> None:
        data = self._load()
        data["decisions"].append(decision)
        self._save(data)

    async def save_goal(self, goal: Dict[str, Any]) -> None:
        data = self._load()
        data["goals"].append(goal)
        self._save(data)

    async def update_goal(self, goal_id: str, current_step: int, status: str) -> None:
        data = self._load()
        for g in data.get("goals", []):
            if g.get("id") == goal_id:
                g["current_step"] = current_step
                g["status"] = status
                break
        self._save(data)

    async def get_stats(self) -> Dict[str, Any]:
        data = self._load()
        return {
            "events": len(data.get("events", [])),
            "goals": len(data.get("goals", [])),
            "decisions": len(data.get("decisions", [])),
        }
