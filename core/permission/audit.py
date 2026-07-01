from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from core.permission.models import AuditEntry, Decision

logger = logging.getLogger(__name__)


class PermissionAudit:
    def __init__(self, storage_path: str | None = None) -> None:
        if storage_path:
            self._path = Path(storage_path)
        else:
            self._path = Path.home() / ".jarvis" / "permission_audit.jsonl"
        self._entries: list[AuditEntry] = []
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("", encoding="utf-8")

    def record(
        self,
        capability_id: str,
        permission_id: str,
        decision: Decision,
        policy: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            timestamp=time.time(),
            capability_id=capability_id,
            permission_id=permission_id,
            decision=decision,
            policy=policy,
            reason=reason,
            details=details or {},
        )
        self._entries.append(entry)
        self._persist(entry)
        return entry

    def _persist(self, entry: AuditEntry) -> None:
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": entry.timestamp,
                    "capability_id": entry.capability_id,
                    "permission_id": entry.permission_id,
                    "decision": entry.decision.value,
                    "policy": entry.policy,
                    "reason": entry.reason,
                    "details": entry.details,
                }) + "\n")
        except OSError:
            logger.warning("[PermissionAudit] Failed to persist entry")

    def recent(self, limit: int = 50) -> list[AuditEntry]:
        return self._entries[-limit:]

    def by_capability(self, capability_id: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.capability_id == capability_id]

    def by_decision(self, decision: Decision) -> list[AuditEntry]:
        return [e for e in self._entries if e.decision == decision]

    def clear(self) -> None:
        self._entries.clear()
        self._path.write_text("", encoding="utf-8")


permission_audit = PermissionAudit()
