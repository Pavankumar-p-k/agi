from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class GoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Goal:
    """A persistent goal with progress tracking, blockers, and next action.

    Example:
        Goal(
            objective="Build Android App",
            progress=0.65,
            next_action="Generate login screen",
            blockers=["Firebase key missing"],
        )
    """
    objective: str
    status: GoalStatus = GoalStatus.ACTIVE
    progress: float = 0.0
    priority: int = 0
    parent_goal_id: str | None = None
    blockers: list[str] = field(default_factory=list)
    next_action: str = ""
    tags: list[str] = field(default_factory=list)
    result: str = ""
    deadline: str = ""
    id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "objective": self.objective,
            "status": self.status.value,
            "progress": self.progress,
            "priority": self.priority,
            "parent_goal_id": self.parent_goal_id,
            "blockers": self.blockers,
            "next_action": self.next_action,
            "tags": self.tags,
            "result": self.result,
            "deadline": self.deadline,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Goal:
        return cls(
            id=data.get("id", ""),
            objective=data.get("objective", ""),
            status=GoalStatus(data.get("status", "active")),
            progress=float(data.get("progress", 0.0)),
            priority=int(data.get("priority", 0)),
            parent_goal_id=data.get("parent_goal_id"),
            blockers=data.get("blockers", []),
            next_action=data.get("next_action", ""),
            tags=data.get("tags", []),
            result=data.get("result", ""),
            deadline=data.get("deadline", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
