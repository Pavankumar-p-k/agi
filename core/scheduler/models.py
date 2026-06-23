"""ScheduledActivity — the unit of work the scheduler manages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ScheduledActivity:
    """A single schedulable unit — wraps an activity_id with priority and state.

    The scheduler does NOT re-model the activity graph. It reads from
    ActivityManager and wraps each active activity with its own metadata:
    priority, score, dependency list, resume tracking.
    """

    activity_id: str
    priority: int = 0
    score: int = 0
    status: str = "pending"
    goal: str = ""
    node_type: str = "goal"
    depends_on: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    resumed_count: int = 0
    last_resumed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return self.status == "pending"

    @property
    def is_blocked(self) -> bool:
        return self.status == "blocked"

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    def block(self) -> None:
        self.status = "blocked"

    def unblock(self) -> None:
        self.status = "pending"


def activity_status_from_node(node_status: str) -> str:
    """Map ActivityStatus string to scheduler status string."""
    terminal = {"COMPLETED", "FAILED", "CANCELLED"}
    if node_status in terminal:
        return "completed"
    if node_status == "RUNNING":
        return "running"
    return "pending"
