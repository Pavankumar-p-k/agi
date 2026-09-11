from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ScheduleModel:
    schedule_id: str = ""
    name: str = ""
    activities: list[Any] = field(default_factory=list)


@dataclass
class ScheduledActivity:
    activity_id: str
    status: str = "pending"
    priority: int = 0
    goal: str = ""
    node_type: str = "goal"
    created_at: datetime = field(default_factory=datetime.now)
    last_resumed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    _blocked: bool = False

    @property
    def is_blocked(self) -> bool:
        return self._blocked

    @property
    def is_ready(self) -> bool:
        return not self._blocked and self.status in {"pending", "running", "suspended"}

    def block(self) -> None:
        self._blocked = True

    def unblock(self) -> None:
        self._blocked = False


def activity_status_from_node(status: Any) -> str:
    value = getattr(status, "value", status)
    value = str(value).upper()
    if value in {"COMPLETED", "FAILED", "CANCELLED"}:
        return "completed"
    if value == "RUNNING":
        return "running"
    if value == "SUSPENDED":
        return "suspended"
    return "pending"
