from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STORE_PATH = Path.home() / ".jarvis" / "commitments.json"


class CommitmentTracker:
    """Tracks inferred follow-up commitments from conversations — matching OpenClaw's commitments system."""

    def __init__(self):
        self._commitments: dict[str, dict] = {}
        self._load()

    def _load(self):
        try:
            if STORE_PATH.exists():
                data = json.loads(STORE_PATH.read_text())
                self._commitments = {c["id"]: c for c in data}
                logger.info("[Commitments] Loaded %d commitments", len(self._commitments))
        except Exception as e:
            logger.warning("[Commitments] Load failed: %s", e)

    def _save(self):
        try:
            STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STORE_PATH.write_text(json.dumps(list(self._commitments.values()), indent=2))
        except Exception as e:
            logger.warning("[Commitments] Save failed: %s", e)

    def _next_id(self) -> str:
        import uuid
        return f"cmt_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{uuid.uuid4().hex[:8]}"

    def add(self, description: str, source: str = "conversation",
            due: str | None = None, priority: str = "medium",
            tags: list[str] | None = None) -> dict:
        cmt = {
            "id": self._next_id(),
            "description": description,
            "source": source,
            "status": "pending",
            "priority": priority,
            "tags": tags or [],
            "created": datetime.now().isoformat(),
            "due": due,
            "completed_at": None,
        }
        self._commitments[cmt["id"]] = cmt
        self._save()
        logger.info("[Commitments] Added: %.60s", description)
        return cmt

    def complete(self, cmt_id: str) -> bool:
        cmt = self._commitments.get(cmt_id)
        if cmt:
            cmt["status"] = "completed"
            cmt["completed_at"] = datetime.now().isoformat()
            self._save()
            return True
        return False

    def dismiss(self, cmt_id: str) -> bool:
        cmt = self._commitments.get(cmt_id)
        if cmt:
            cmt["status"] = "dismissed"
            self._save()
            return True
        return False

    def list(self, status: str | None = None) -> list[dict]:
        items = list(self._commitments.values())
        if status:
            items = [c for c in items if c["status"] == status]
        return sorted(items, key=lambda c: c.get("due") or c["created"])

    def get_overdue(self) -> list[dict]:
        now = datetime.now()
        overdue = []
        for c in self._commitments.values():
            if c["status"] != "pending":
                continue
            if c.get("due"):
                due = datetime.fromisoformat(c["due"])
                if due < now:
                    overdue.append(c)
        return overdue

    def infer_from_text(self, text: str, source: str = "conversation") -> list[dict]:
        patterns = [
            r"(?:I'?ll|I will|let me|I need to|I have to|I should|I'm going to)\s+(.+?)(?:[.!,]|$)",
            r"(?:remind me to|remind myself to)\s+(.+?)(?:[.!,]|$)",
            r"(?:don'?t forget to|must remember to)\s+(.+?)(?:[.!,]|$)",
            r"(?:next time|tomorrow|by\s+\w+day)\s+(?:I'?ll|I will|I need to)\s+(.+?)(?:[.!,]|$)",
        ]
        found = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                desc = match.group(1).strip()
                if len(desc) > 10:
                    cmt = self.add(description=desc, source=source)
                    found.append(cmt)
        return found

    def stats(self) -> dict[str, Any]:
        total = len(self._commitments)
        pending = sum(1 for c in self._commitments.values() if c["status"] == "pending")
        completed = sum(1 for c in self._commitments.values() if c["status"] == "completed")
        dismissed = sum(1 for c in self._commitments.values() if c["status"] == "dismissed")
        overdue = len(self.get_overdue())
        return {
            "total": total,
            "pending": pending,
            "completed": completed,
            "dismissed": dismissed,
            "overdue": overdue,
        }


commitment_tracker = CommitmentTracker()
