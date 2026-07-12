from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol


class PlanStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


@dataclass
class Plan:
    id: str
    goal: str
    status: PlanStatus = PlanStatus.DRAFT
    priority: int = 0
    progress: float = 0.0
    parent_plan_id: str | None = None
    root_node: dict[str, Any] | None = None
    blockers: list[str] = field(default_factory=list)
    next_action: str = ""
    tags: list[str] = field(default_factory=list)
    result: str = ""
    deadline: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status.value,
            "priority": self.priority,
            "progress": self.progress,
            "parent_plan_id": self.parent_plan_id,
            "root_node": self.root_node,
            "blockers": self.blockers,
            "next_action": self.next_action,
            "tags": self.tags,
            "result": self.result,
            "deadline": self.deadline,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Plan:
        return cls(
            id=data.get("id", ""),
            goal=data.get("goal", data.get("objective", "")),
            status=PlanStatus(data.get("status", "draft")),
            priority=int(data.get("priority", 0)),
            progress=float(data.get("progress", 0.0)),
            parent_plan_id=data.get("parent_plan_id", data.get("parent_goal_id")),
            root_node=data.get("root_node"),
            blockers=data.get("blockers", []),
            next_action=data.get("next_action", ""),
            tags=data.get("tags", []),
            result=data.get("result", ""),
            deadline=data.get("deadline", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    @classmethod
    def from_goal_dict(cls, data: dict) -> Plan:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            goal=data.get("objective", ""),
            status=PlanStatus(data.get("status", "active")),
            priority=int(data.get("priority", 0)),
            progress=float(data.get("progress", 0.0)),
            parent_plan_id=data.get("parent_goal_id"),
            blockers=data.get("blockers", []),
            next_action=data.get("next_action", ""),
            tags=data.get("tags", []),
            result=data.get("result", ""),
            deadline=data.get("deadline", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )


class Planner(Protocol):
    def create_plan(self, goal: str, context: dict[str, Any] | None = None) -> Plan:
        ...

    def replan(self, plan: Plan, error_context: dict[str, Any] | None = None) -> Plan:
        ...
