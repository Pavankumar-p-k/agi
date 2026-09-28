"""RuntimeObserver — detects providers using undeclared permissions (Gate 8)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from core.permission.models import AuditEntry, Decision

_QUARANTINE_THRESHOLD = 3


@dataclass
class Violation:
    provider_id: str
    permission_id: str
    timestamp: float = field(default_factory=time.time)


class RuntimeObserver:
    def __init__(self) -> None:
        self._declared: dict[str, frozenset] = {}
        self._violations: dict[str, list] = {}
        self._quarantined: set = set()
        self._lock = threading.Lock()

    def declare(self, provider_id: str, permissions: frozenset) -> None:
        with self._lock:
            self._declared[provider_id] = frozenset(permissions)

    def observe(self, provider_id: str, permission_id: str) -> bool:
        """Record a permission use; True when it was a violation."""
        with self._lock:
            declared = self._declared.get(provider_id)
            if declared is None or permission_id in declared:
                return False
            self._violations.setdefault(provider_id, []).append(
                Violation(provider_id=provider_id, permission_id=permission_id))
            if len(self._violations[provider_id]) >= _QUARANTINE_THRESHOLD:
                self._quarantined.add(provider_id)
            return True

    def violations_for(self, provider_id: str) -> list:
        with self._lock:
            return list(self._violations.get(provider_id, []))

    def violation_count(self, provider_id: str) -> int:
        with self._lock:
            return len(self._violations.get(provider_id, []))

    def should_quarantine(self, provider_id: str) -> bool:
        with self._lock:
            return provider_id in self._quarantined

    def quarantine(self, provider_id: str) -> None:
        with self._lock:
            self._quarantined.add(provider_id)


__all__ = ["RuntimeObserver", "Violation"]
