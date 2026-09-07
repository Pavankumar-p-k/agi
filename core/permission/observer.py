"""
Module: core.permission.observer
Runtime observation of permission enforcement and violations.
"""
from __future__ import annotations
from typing import Any, Callable, Optional, FrozenSet
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
import uuid

from core.permission.models import Decision, RiskLevel

logger = logging.getLogger(__name__)


class ObservationType(Enum):
    PERMISSION_CHECK = "permission_check"
    VIOLATION = "violation"
    ESCALATION = "escalation"
    POLICY_CHANGE = "policy_change"
    RATE_LIMIT = "rate_limit"


@dataclass
class Observation:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    observation_type: ObservationType = ObservationType.PERMISSION_CHECK
    permission_name: str = ""
    decision: Decision = Decision.ALLOW
    requester: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "type": self.observation_type.value,
            "permission_name": self.permission_name,
            "decision": self.decision.value,
            "requester": self.requester,
            "details": self.details,
        }


@dataclass
class ViolationRecord:
    permission_id: str = ""
    provider_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RuntimeObserver:
    def __init__(self):
        self._declared: dict[str, frozenset[str]] = {}
        self._violations: dict[str, list[ViolationRecord]] = {}
        self._quarantine_threshold: int = 3

    def declare(self, provider_id: str, permissions: frozenset[str]) -> None:
        self._declared[provider_id] = permissions
        self._violations.setdefault(provider_id, [])

    def observe(self, provider_id: str, permission_id: str) -> None:
        declared = self._declared.get(provider_id, frozenset())
        if permission_id not in declared:
            self._violations.setdefault(provider_id, []).append(
                ViolationRecord(permission_id=permission_id, provider_id=provider_id)
            )

    def violations_for(self, provider_id: str) -> list[ViolationRecord]:
        return list(self._violations.get(provider_id, []))

    def violation_count(self, provider_id: str) -> int:
        return len(self._violations.get(provider_id, []))

    def should_quarantine(self, provider_id: str) -> bool:
        return self.violation_count(provider_id) >= self._quarantine_threshold

    def clear(self) -> int:
        count = sum(len(v) for v in self._violations.values())
        self._declared.clear()
        self._violations.clear()
        return count

    def to_dict(self) -> dict[str, Any]:
        return {
            "declared": {k: list(v) for k, v in self._declared.items()},
            "violations": {k: len(v) for k, v in self._violations.items()},
        }
