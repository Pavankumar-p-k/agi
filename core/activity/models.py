"""Activity data models — nodes, edges, statuses for the activity graph."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class ActivityStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


NODE_TYPES = frozenset({
    "goal", "subgoal", "agent_call", "tool_call", "artifact", "milestone",
})

EDGE_TYPES = frozenset({
    "depends_on", "produces", "triggers", "references",
})


@dataclass
class ActivityNode:
    """A single node in the activity graph.

    Every unit of work — from a user goal down to a single tool call —
    is represented as a node. Nodes form a tree via parent_id and can
    express causality via origin_node_id.

    Every node carries a ``resource_scope`` dict (tenant_id, workspace_id,
    owner_id) inherited from the ``PipelineContext`` that created it.
    Cross-tenant parent/child relationships are rejected.
    """
    node_id: str
    activity_id: str                       # root node id for grouping
    node_type: str                         # goal | subgoal | agent_call | tool_call | artifact | milestone
    label: str                             # human-readable description
    status: ActivityStatus = ActivityStatus.PENDING
    depth: int = 0                         # 0 = root goal, 1 = child, etc.
    parent_id: str | None = None           # hierarchical parent
    agent_id: str | None = None            # who executed this (None for structural nodes)
    origin_node_id: str | None = None      # causality — "what caused this node to exist"
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)   # key -> artifact_id
    workflow_id: str | None = None         # linked WorkflowInstance (if spawned)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    resource_scope: dict[str, Any] = field(default_factory=dict)
    """Tenant ownership scope: ``{"tenant_id": ..., "workspace_id": ..., "owner_id": ...}``.
    Inherited from the PipelineContext that created the activity."""
    created_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            ActivityStatus.COMPLETED,
            ActivityStatus.FAILED,
            ActivityStatus.CANCELLED,
        )

    @property
    def is_incomplete(self) -> bool:
        return self.status in (
            ActivityStatus.PENDING,
            ActivityStatus.RUNNING,
            ActivityStatus.SUSPENDED,
        )


@dataclass
class ActivityEdge:
    """A directed edge between two activity nodes.

    Expresses dependencies, causality, or loose references.
    """
    edge_id: str
    from_node_id: str
    to_node_id: str
    edge_type: str = "depends_on"          # depends_on | produces | triggers | references
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
