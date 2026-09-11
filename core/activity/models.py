from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class ActivityStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class ActivityNode:
    node_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    activity_id: str = ""
    node_type: str = "goal"
    label: str = ""
    depth: int = 0
    status: ActivityStatus = ActivityStatus.PENDING
    parent_id: str | None = None
    agent_id: str | None = None
    workflow_id: str | None = None
    origin_node_id: str | None = None
    input: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def activity_id(self) -> str:
        return self._activity_id if hasattr(self, "_activity_id") else self.node_id

    @activity_id.setter
    def activity_id(self, value: str) -> None:
        self._activity_id = value


@dataclass
class ActivityEdge:
    edge_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    from_node_id: str = ""
    to_node_id: str = ""
    edge_type: str = "depends_on"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
