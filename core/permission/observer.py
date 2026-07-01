from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from core.permission.models import HIGH_RISK

logger = logging.getLogger(__name__)


@dataclass
class ObservedAction:
    provider_id: str
    permission_id: str
    timestamp: float
    blocked: bool = False


@dataclass
class ViolationRecord:
    provider_id: str
    permission_id: str
    observed_at: float
    reason: str


class RuntimeObserver:
    def __init__(self) -> None:
        self._declared: dict[str, frozenset[str]] = {}
        self._observed: list[ObservedAction] = []
        self._violations: list[ViolationRecord] = []

    def declare(self, provider_id: str, permissions: frozenset[str]) -> None:
        self._declared[provider_id] = permissions

    def observe(self, provider_id: str, permission_id: str) -> None:
        action = ObservedAction(
            provider_id=provider_id,
            permission_id=permission_id,
            timestamp=time.time(),
        )
        self._observed.append(action)

        declared = self._declared.get(provider_id, frozenset())
        if permission_id not in declared:
            record = ViolationRecord(
                provider_id=provider_id,
                permission_id=permission_id,
                observed_at=action.timestamp,
                reason=f"Permission '{permission_id}' not in declared set for provider '{provider_id}'",
            )
            self._violations.append(record)
            action.blocked = True
            logger.warning(
                "[RuntimeObserver] VIOLATION: %s used %s without declaring it",
                provider_id, permission_id,
            )

    def violations_for(self, provider_id: str) -> list[ViolationRecord]:
        return [v for v in self._violations if v.provider_id == provider_id]

    def recent_violations(self, limit: int = 20) -> list[ViolationRecord]:
        return self._violations[-limit:]

    def violation_count(self, provider_id: str | None = None) -> int:
        if provider_id:
            return len(self.violations_for(provider_id))
        return len(self._violations)

    def should_quarantine(self, provider_id: str, threshold: int = 3) -> bool:
        return self.violation_count(provider_id) >= threshold

    def clear(self) -> None:
        self._declared.clear()
        self._observed.clear()
        self._violations.clear()


runtime_observer = RuntimeObserver()
