"""Activity models — immutable-by-convention activity graph nodes/edges."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid


class ActivityStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            lowered = value.lower()
            for member in cls:
                if member.value == lowered:
                    return member
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ActivityNode:
    node_id: str
    activity_id: str = ""
    node_type: str = "goal"
    label: str = ""
    status: ActivityStatus = ActivityStatus.PENDING
    parent_id: Optional[str] = None
    resource_scope: dict = field(default_factory=dict)
    created_at: Optional[datetime] = field(default_factory=_now)
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)
    depth: int = 0
    agent_id: Optional[str] = None
    workflow_id: Optional[str] = None
    origin_node_id: Optional[str] = None
    input: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "activity_id": self.activity_id,
            "node_type": self.node_type,
            "label": self.label,
            "status": self.status.value,
            "parent_id": self.parent_id,
            "resource_scope": dict(self.resource_scope),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class ActivityEdge:
    edge_id: str = field(default_factory=lambda: f"edge_{uuid.uuid4().hex[:12]}")
    from_node_id: str = ""
    to_node_id: str = ""
    edge_type: str = "follows"
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)

    @property
    def src(self) -> str:
        return self.from_node_id

    @property
    def dst(self) -> str:
        return self.to_node_id

    @property
    def relation(self) -> str:
        return self.edge_type

    def to_dict(self) -> dict:
        return {"src": self.src, "dst": self.dst, "relation": self.relation}


__all__ = ["ActivityNode", "ActivityEdge", "ActivityStatus"]
