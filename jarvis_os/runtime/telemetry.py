from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class TelemetryStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.data_dir / "telemetry.jsonl"

    def record(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_type": event_type,
            "timestamp": time.time(),
            "payload": payload,
        }
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        with self.events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
        return event

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.events_file.exists():
            return []
        rows = [json.loads(line) for line in self.events_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        return rows[-limit:]

    def metrics(self) -> dict[str, Any]:
        events = self.recent(limit=500)
        by_type: dict[str, int] = {}
        tool_calls: dict[str, int] = {}
        failures = 0
        for event in events:
            by_type[event["event_type"]] = by_type.get(event["event_type"], 0) + 1
            payload = event.get("payload", {})
            tool = payload.get("tool")
            if tool:
                tool_calls[tool] = tool_calls.get(tool, 0) + 1
            if payload.get("success") is False:
                failures += 1
        return {
            "events": len(events),
            "failures": failures,
            "by_type": by_type,
            "tool_calls": tool_calls,
        }
