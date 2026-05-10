from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LegacyAGIMemoryAdapter:
    def __init__(self, backend_root: Path) -> None:
        self.backend_root = Path(backend_root)
        self.path = self.backend_root / "data" / "agi_memory.json"

    def status(self) -> dict[str, Any]:
        return {"name": "legacy_agi_memory", "available": self.path.exists(), "path": str(self.path)}

    def stats(self) -> dict[str, Any]:
        payload = self._load()
        return {
            "events": len(payload.get("events", [])),
            "goals": len(payload.get("goals", [])),
            "decisions": len(payload.get("decisions", [])),
            "available": self.path.exists(),
            "path": str(self.path),
        }

    def recent_events(self, limit: int = 10) -> dict[str, Any]:
        payload = self._load()
        events = list(payload.get("events", []))[-limit:]
        return {"events": events, "count": len(events), "available": self.path.exists()}

    def latest_mood(self) -> dict[str, Any]:
        payload = self._load()
        mood = "neutral"
        for event in reversed(payload.get("events", [])):
            if event.get("mood"):
                mood = str(event["mood"])
                break
        return {"mood": mood, "available": self.path.exists()}

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"events": [], "goals": [], "decisions": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"events": [], "goals": [], "decisions": []}
