"""PermissionAudit — append-only decision log (Gate 6)."""
from __future__ import annotations

import threading
import time

from core.permission.models import AuditEntry, Decision


class PermissionAudit:
    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: list = []
        self._lock = threading.Lock()
        self._max = max_entries

    def record(self, capability_id: str, permission_id: str,
               decision: Decision, policy: str = "", reason: str = "",
               **metadata) -> AuditEntry:
        entry = AuditEntry(
            capability_id=capability_id,
            permission_id=permission_id or capability_id,
            decision=decision,
            policy=policy or "default",
            reason=reason or "policy evaluation",
            timestamp=time.time(),
            metadata=dict(metadata),
        )
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max:
                del self._entries[:-self._max]
        return entry

    def recent(self, n: int = 50) -> list:
        with self._lock:
            return list(self._entries[-n:])

    def by_capability(self, capability_id: str) -> list:
        with self._lock:
            return [e for e in self._entries if e.capability_id == capability_id]

    def __len__(self) -> int:
        return len(self._entries)


__all__ = ["PermissionAudit"]
