# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class NodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class GraphNode:
    """A single node in the execution dependency graph."""

    id: str
    description: str = ""
    status: NodeStatus = NodeStatus.PENDING
    depends_on: list[str] = field(default_factory=list)
    result: str = ""
    error: str = ""
    duration_ms: float = 0.0
    agent: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "depends_on": self.depends_on,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "agent": self.agent,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphNode:
        return cls(
            id=data["id"],
            description=data.get("description", ""),
            status=NodeStatus(data.get("status", "pending")),
            depends_on=data.get("depends_on", []),
            result=data.get("result", ""),
            error=data.get("error", ""),
            duration_ms=data.get("duration_ms", 0.0),
            agent=data.get("agent", ""),
            metadata=data.get("metadata", {}),
        )


class ExecutionGraph:
    """A DAG of execution tasks with dependency tracking.

    Supports topological sort, status computation,
    and full JSON serialization for checkpointing.
    """

    SCHEMA_VERSION = 1

    def __init__(self, session_key: str = ""):
        self.session_key = session_key
        self.nodes: dict[str, GraphNode] = {}
        self.created_at = datetime.now(UTC).isoformat()
        self.updated_at = self.created_at

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node
        self.updated_at = datetime.now(UTC).isoformat()

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def update_status(self, node_id: str, status: NodeStatus, **extra) -> None:
        node = self.nodes.get(node_id)
        if node:
            node.status = status
            for k, v in extra.items():
                if hasattr(node, k):
                    setattr(node, k, v)
            self.updated_at = datetime.now(UTC).isoformat()

    def ready_nodes(self) -> list[GraphNode]:
        """Return all pending nodes whose dependencies are completed."""
        completed = {
            nid for nid, n in self.nodes.items()
            if n.status == NodeStatus.COMPLETED
        }
        ready: list[GraphNode] = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            if all(dep in completed for dep in node.depends_on):
                ready.append(node)
        return ready

    def topological_order(self) -> list[GraphNode]:
        """Return nodes in dependency order (reverse topological sort)."""
        visited: set[str] = set()
        order: list[GraphNode] = []

        def _visit(node_id: str) -> None:
            if node_id in visited:
                return
            visited.add(node_id)
            node = self.nodes.get(node_id)
            if node:
                for dep_id in node.depends_on:
                    _visit(dep_id)
                order.append(node)

        for nid in self.nodes:
            _visit(nid)
        return order

    def is_complete(self) -> bool:
        """Check if all nodes are in a terminal state."""
        if not self.nodes:
            return False
        return all(
            n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED)
            for n in self.nodes.values()
        )

    def completion_pct(self) -> float:
        """Percentage of nodes in a terminal state."""
        if not self.nodes:
            return 0.0
        terminal = sum(
            1 for n in self.nodes.values()
            if n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED)
        )
        return round(terminal / len(self.nodes) * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "session_key": self.session_key,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionGraph:
        graph = cls(session_key=data.get("session_key", ""))
        graph.created_at = data.get("created_at", graph.created_at)
        graph.updated_at = data.get("updated_at", graph.updated_at)
        for node_data in data.get("nodes", []):
            node = GraphNode.from_dict(node_data)
            graph.nodes[node.id] = node
        return graph

    @classmethod
    def from_json(cls, json_str: str) -> ExecutionGraph:
        return cls.from_dict(json.loads(json_str))
