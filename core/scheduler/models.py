"""Scheduler models — ScheduledActivity with tenant partitioning."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ActivityStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def activity_status_from_node(status: Any) -> ActivityStatus:
    """Map a generic status value onto the scheduler ActivityStatus."""
    if isinstance(status, ActivityStatus):
        return status
    try:
        return ActivityStatus(str(getattr(status, "value", status)).lower())
    except ValueError:
        return ActivityStatus.PENDING


@dataclass
class ScheduledActivity:
    activity_id: str
    goal: str = ""
    priority: int = 1
    tenant_id: str = "default"
    status: ActivityStatus = ActivityStatus.PENDING
    ready_at: Optional[datetime] = None
    payload: dict = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        if self.status == ActivityStatus.READY:
            return True
        if self.ready_at is None:
            return self.status == ActivityStatus.PENDING
        return self.ready_at <= datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "goal": self.goal,
            "priority": self.priority,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
        }


__all__ = ["ActivityStatus", "ScheduledActivity", "activity_status_from_node"]
