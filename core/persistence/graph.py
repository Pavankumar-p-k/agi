from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class GraphNode:
    id: str = ""
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "depends_on": list(self.depends_on),
            "status": self.status.value,
            "result": self.result,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphNode":
        if not data:
            return cls()
        return cls(
            id=str(data.get("id", "")),
            description=str(data.get("description", "")),
            depends_on=list(data.get("depends_on") or []),
            status=NodeStatus(data.get("status", NodeStatus.PENDING.value)),
            result=data.get("result"),
            duration_ms=data.get("duration_ms"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ExecutionGraph:
    session_key: str = ""
    nodes: dict[str, GraphNode] = field(default_factory=dict)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def update_status(self, node_id: str, status: NodeStatus) -> None:
        node = self.get_node(node_id)
        if node:
            node.status = status

    def topological_order(self) -> list[GraphNode]:
        indeg: dict[str, int] = {nid: 0 for nid in self.nodes}
        dependents: dict[str, list[str]] = defaultdict(list)
        for nid, node in self.nodes.items():
            for dep in node.depends_on:
                if dep in self.nodes:
                    indeg[nid] += 1
                    dependents[dep].append(nid)

        q = deque(sorted(nid for nid, deg in indeg.items() if deg == 0))
        order: list[GraphNode] = []
        while q:
            nid = q.popleft()
            order.append(self.nodes[nid])
            for child in sorted(dependents.get(nid, [])):
                indeg[child] -= 1
                if indeg[child] == 0:
                    q.append(child)
        return order

    def ready_nodes(self) -> list[GraphNode]:
        if not self.nodes:
            return []
        completed = {nid for nid, node in self.nodes.items() if node.status == NodeStatus.COMPLETED}
        ready: list[GraphNode] = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            if all(dep in completed for dep in node.depends_on if dep in self.nodes):
                ready.append(node)
        return ready

    def is_complete(self) -> bool:
        if not self.nodes:
            return False
        return all(node.status in (NodeStatus.COMPLETED, NodeStatus.FAILED) for node in self.nodes.values())

    def completion_pct(self) -> float:
        if not self.nodes:
            return 0.0
        completed = sum(1 for node in self.nodes.values() if node.status == NodeStatus.COMPLETED)
        return round((completed / len(self.nodes)) * 100.0, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_key": self.session_key,
            "nodes": [node.to_dict() for node in self.nodes.values()],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionGraph":
        graph = cls(session_key=str(data.get("session_key", "")))
        for item in data.get("nodes", []) or []:
            graph.add_node(GraphNode.from_dict(item))
        return graph

    @classmethod
    def from_json(cls, payload: str) -> "ExecutionGraph":
        return cls.from_dict(json.loads(payload))
