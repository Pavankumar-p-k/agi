from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable


class SchedulerService:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.schedule_file = self.data_dir / "schedules.json"
        self._submitter: Callable[[str], dict[str, Any]] | None = None

    def bind_submitter(self, submitter: Callable[[str], dict[str, Any]]) -> None:
        self._submitter = submitter

    def _load(self) -> list[dict[str, Any]]:
        if not self.schedule_file.exists():
            return []
        raw = self.schedule_file.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        items = []
        for item in payload:
            normalized = {
                "name": item["name"],
                "command": item["command"],
                "interval_s": int(item.get("interval_s", 3600)),
                "created_at": float(item.get("created_at", time.time())),
                "last_run_at": item.get("last_run_at"),
                "next_run_at": float(item.get("next_run_at", time.time())),
                "enabled": bool(item.get("enabled", True)),
                "last_job_id": item.get("last_job_id", ""),
            }
            items.append(normalized)
        return items

    def _save(self, items: list[dict[str, Any]]) -> None:
        self.schedule_file.write_text(json.dumps(items, indent=2), encoding="utf-8")

    def list(self) -> list[dict[str, Any]]:
        return self._load()

    def due(self, now: float | None = None) -> list[dict[str, Any]]:
        current = now if now is not None else time.time()
        return [item for item in self._load() if item.get("enabled", True) and item.get("next_run_at", current) <= current]

    def run_due(self, now: float | None = None) -> dict[str, Any]:
        if self._submitter is None:
            return {"triggered": 0, "jobs": [], "error": "submitter not bound"}
        current = now if now is not None else time.time()
        items = self._load()
        triggered = []
        for item in items:
            if not item.get("enabled", True):
                continue
            if item.get("next_run_at", current) > current:
                continue
            submission = self._submitter(item["command"])
            job = submission.get("job", {})
            item["last_run_at"] = current
            item["next_run_at"] = current + int(item["interval_s"])
            item["last_job_id"] = job.get("job_id", "")
            triggered.append({"name": item["name"], "job_id": item["last_job_id"], "command": item["command"]})
        self._save(items)
        return {"triggered": len(triggered), "jobs": triggered}
