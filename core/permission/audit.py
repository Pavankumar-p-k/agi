"""
Module: core.permission.audit
Audit trail for permission decisions and violations.
"""
from __future__ import annotations
from typing import Any, Optional
from dataclasses import dataclass, field
import time
import logging

from core.permission.models import AuditEntry, Decision, RiskLevel

logger = logging.getLogger(__name__)


@dataclass
class PermissionAudit:
    entries: list[AuditEntry] = field(default_factory=list)
    max_entries: int = 10000
    violation_callbacks: list = field(default_factory=list)

    def record(self, permission_name: str, decision: Decision, requester: str = "", resource: str = "", risk_level: RiskLevel = RiskLevel.MEDIUM, reason: str = "", metadata: dict[str, Any] | None = None, violation: bool = False, capability_id: str = "", policy: str = "") -> AuditEntry:
        entry = AuditEntry(
            permission_name=permission_name,
            decision=decision,
            requester=requester,
            resource=resource,
            risk_level=risk_level,
            reason=reason,
            metadata=metadata or {},
            violation=violation,
            capability_id=capability_id,
            policy=policy,
        )
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        if violation:
            self._notify_violation(entry)
        return entry

    def _notify_violation(self, entry: AuditEntry) -> None:
        for cb in self.violation_callbacks:
            try:
                cb(entry)
            except Exception:
                logger.exception("Violation callback failed")

    def on_violation(self, callback: Any) -> None:
        self.violation_callbacks.append(callback)

    def recent(self, limit: int = 100) -> list[AuditEntry]:
        return self.entries[-limit:]

    def by_capability(self, capability_id: str) -> list[AuditEntry]:
        return [e for e in self.entries if e.capability_id == capability_id]

    def query(self, permission_name: str | None = None, decision: Decision | None = None, requester: str | None = None, violation_only: bool = False, limit: int = 100) -> list[AuditEntry]:
        results = self.entries
        if permission_name:
            results = [e for e in results if e.permission_name == permission_name]
        if decision:
            results = [e for e in results if e.decision == decision]
        if requester:
            results = [e for e in results if e.requester == requester]
        if violation_only:
            results = [e for e in results if e.violation]
        return results[-limit:]

    def count_violations(self) -> int:
        return sum(1 for e in self.entries if e.violation)

    def clear(self) -> int:
        count = len(self.entries)
        self.entries.clear()
        return count

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_entries": len(self.entries),
            "violations": self.count_violations(),
            "recent": [e.to_dict() for e in self.entries[-10:]],
        }


def permission_audit(**kwargs: Any) -> PermissionAudit:
    return PermissionAudit(**kwargs)
