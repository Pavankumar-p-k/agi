"""Deterministic phase-aware graph used by the parallel agent executor."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class GraphNode:
    node_id: str
    agent_id: str
    goal: str
    phase: int = 50
    parameters: dict[str, Any] = field(default_factory=dict)
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return self.completed_at - self.started_at

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphNode":
        values = dict(data)
        values["status"] = NodeStatus(values.get("status", NodeStatus.PENDING))
        return cls(**values)


@dataclass
class AgentExecutionGraph:
    max_parallel: int = 3
    nodes: dict[str, GraphNode] = field(default_factory=dict)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    @property
    def is_complete(self) -> bool:
        return all(n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED) for n in self.nodes.values())

    @property
    def is_blocked(self) -> bool:
        phases = sorted({n.phase for n in self.nodes.values()})
        for phase in phases:
            current = [n for n in self.nodes.values() if n.phase == phase]
            if current and all(n.status == NodeStatus.FAILED for n in current):
                return any(n.status == NodeStatus.PENDING and n.phase > phase for n in self.nodes.values())
        return False

    def get_ready_nodes(self) -> list[GraphNode]:
        pending = [n for n in self.nodes.values() if n.status == NodeStatus.PENDING]
        if not pending:
            return []
        phase = min(n.phase for n in pending)
        return [n for n in pending if n.phase == phase][: max(1, self.max_parallel)]

    def mark_running(self, node_id: str) -> None:
        node = self.nodes[node_id]
        node.status = NodeStatus.RUNNING
        node.started_at = time.time()

    def mark_completed(self, node_id: str, result: Any = None, artifacts: dict[str, Any] | None = None) -> None:
        node = self.nodes[node_id]
        node.status = NodeStatus.COMPLETED
        node.result = result
        if artifacts:
            node.artifacts.update(artifacts)
        node.completed_at = time.time()

    def mark_failed(self, node_id: str, error: str) -> None:
        node = self.nodes[node_id]
        node.status = NodeStatus.FAILED
        node.error = str(error)
        node.completed_at = time.time()

    def get_all_artifacts(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for node in self.nodes.values():
            merged.update(node.artifacts)
        return merged

    def to_dict(self) -> dict[str, Any]:
        return {"max_parallel": self.max_parallel, "nodes": [n.to_dict() for n in self.nodes.values()]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentExecutionGraph":
        graph = cls(max_parallel=int(data.get("max_parallel", 3)))
        for item in data.get("nodes", []):
            node = GraphNode.from_dict(item)
            graph.add_node(node)
        return graph


_PHASES = {
    "research": 0,
    "build": 1,
    "test": 2,
    "deploy": 3,
    "browser": 4,
    "code": 5,
    "email": 6,
}


def get_phase_for_step(step: str) -> int:
    return _PHASES.get(str(step).casefold(), 50)


def build_graph_from_tasks(tasks: list[dict[str, Any]], max_parallel: int = 3) -> AgentExecutionGraph:
    graph = AgentExecutionGraph(max_parallel=max_parallel)
    for index, task in enumerate(tasks):
        node_id = str(task.get("node_id") or task.get("id") or f"node_{index}")
        graph.add_node(GraphNode(
            node_id=node_id,
            agent_id=str(task.get("agent_id", "")),
            goal=str(task.get("goal", "")),
            phase=int(task.get("phase", get_phase_for_step(task.get("step", "")))),
            parameters=dict(task.get("parameters") or {}),
        ))
    return graph
