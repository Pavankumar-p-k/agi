from __future__ import annotations

import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TaskNode:
    """A single node in the task dependency graph (DAG)."""
    id: str = ""
    label: str = ""
    description: str = ""
    status: str = "pending"
    depends_on: list[str] = field(default_factory=list)
    agent_type: str = "general"
    tools_allowed: list[str] = field(default_factory=lambda: ["*"])
    result: str = ""
    error: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "status": self.status,
            "depends_on": self.depends_on,
            "agent_type": self.agent_type,
            "tools_allowed": self.tools_allowed,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TaskNode:
        return cls(
            id=data.get("id", ""),
            label=data.get("label", ""),
            description=data.get("description", ""),
            status=data.get("status", "pending"),
            depends_on=data.get("depends_on", []),
            agent_type=data.get("agent_type", "general"),
            tools_allowed=data.get("tools_allowed", ["*"]),
            result=data.get("result", ""),
            error=data.get("error", ""),
            metadata=data.get("metadata", {}),
        )


class TaskGraph:
    """A DAG-based task dependency graph.

    Tasks are nodes with dependencies expressed as edges (depends_on).
    Supports topological sort, execution queue generation, cycle detection,
    and critical path analysis.
    """

    def __init__(self):
        self._nodes: dict[str, TaskNode] = {}
        self._goal_id: str = ""

    def add_node(self, label: str, description: str = "",
                 depends_on: list[str] | None = None,
                 agent_type: str = "general",
                 tools_allowed: list[str] | None = None,
                 node_id: str | None = None) -> TaskNode:
        nid = node_id or str(uuid.uuid4())
        node = TaskNode(
            id=nid,
            label=label,
            description=description,
            depends_on=depends_on or [],
            agent_type=agent_type,
            tools_allowed=tools_allowed or ["*"],
        )
        self._nodes[nid] = node
        return node

    def get_node(self, node_id: str) -> TaskNode | None:
        return self._nodes.get(node_id)

    def remove_node(self, node_id: str) -> bool:
        if node_id in self._nodes:
            del self._nodes[node_id]
            for node in self._nodes.values():
                if node_id in node.depends_on:
                    node.depends_on.remove(node_id)
            return True
        return False

    def add_dependency(self, node_id: str, depends_on_id: str) -> bool:
        if node_id not in self._nodes or depends_on_id not in self._nodes:
            return False
        if depends_on_id not in self._nodes[node_id].depends_on:
            self._nodes[node_id].depends_on.append(depends_on_id)
        return True

    def has_cycle(self) -> bool:
        visited = set()
        in_progress = set()

        def _dfs(nid: str) -> bool:
            if nid in in_progress:
                return True
            if nid in visited:
                return False
            in_progress.add(nid)
            node = self._nodes.get(nid)
            if node:
                for dep_id in node.depends_on:
                    if dep_id in self._nodes and _dfs(dep_id):
                        return True
            in_progress.discard(nid)
            visited.add(nid)
            return False

        for nid in list(self._nodes.keys()):
            if nid not in visited:
                if _dfs(nid):
                    logger.warning("[TaskGraph] cycle detected")
                    return True
        return False

    def topological_sort(self) -> list[TaskNode]:
        in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}
        adjacency: dict[str, list[str]] = {nid: [] for nid in self._nodes}

        for nid, node in self._nodes.items():
            for dep_id in node.depends_on:
                if dep_id in adjacency:
                    adjacency[dep_id].append(nid)
                    in_degree[nid] = in_degree.get(nid, 0) + 1

        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        sorted_nodes = []

        while queue:
            nid = queue.popleft()
            sorted_nodes.append(self._nodes[nid])
            for neighbor in adjacency.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_nodes) != len(self._nodes):
            remaining = set(self._nodes.keys()) - {n.id for n in sorted_nodes}
            for rid in remaining:
                sorted_nodes.append(self._nodes[rid])

        return sorted_nodes

    def get_execution_queue(self) -> list[TaskNode]:
        ready = []
        for node in self._nodes.values():
            if node.status != "pending":
                continue
            deps_satisfied = all(
                self._nodes.get(dep_id) and self._nodes[dep_id].status == "completed"
                for dep_id in node.depends_on
                if dep_id in self._nodes
            )
            if deps_satisfied:
                ready.append(node)

        ready.sort(key=lambda n: -len([
            other for other in self._nodes.values()
            if n.id in other.depends_on
        ]))
        return ready

    def mark_completed(self, node_id: str, result: str = ""):
        if node_id in self._nodes:
            self._nodes[node_id].status = "completed"
            self._nodes[node_id].result = result

    def mark_failed(self, node_id: str, error: str = ""):
        if node_id in self._nodes:
            self._nodes[node_id].status = "failed"
            self._nodes[node_id].error = error
            for node in self._nodes.values():
                if node_id in node.depends_on:
                    node.status = "blocked"

    def mark_running(self, node_id: str):
        if node_id in self._nodes:
            self._nodes[node_id].status = "running"

    def get_critical_path(self) -> list[TaskNode]:
        topo = self.topological_sort()
        dist: dict[str, int] = {}
        prev: dict[str, str | None] = {}

        for node in topo:
            dist[node.id] = max(
                [dist.get(dep, 0) + 1 for dep in node.depends_on if dep in self._nodes] or [0]
            )
            if node.depends_on:
                best_dep = max(
                    [dep for dep in node.depends_on if dep in self._nodes],
                    key=lambda d: dist.get(d, 0),
                    default=None,
                )
                prev[node.id] = best_dep
            else:
                prev[node.id] = None

        if not dist:
            return []

        last_id = max(dist, key=lambda k: dist[k])
        path = []
        current = last_id
        while current:
            if current in self._nodes:
                path.append(self._nodes[current])
            current = prev.get(current)
        path.reverse()
        return path

    def to_dict(self) -> dict:
        return {
            "goal_id": self._goal_id,
            "nodes": {nid: node.to_dict() for nid, node in self._nodes.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> TaskGraph:
        graph = cls()
        graph._goal_id = data.get("goal_id", "")
        for nid, node_data in data.get("nodes", {}).items():
            graph._nodes[nid] = TaskNode.from_dict(node_data)
        return graph

    def __len__(self) -> int:
        return len(self._nodes)

    @property
    def nodes(self) -> dict[str, TaskNode]:
        return self._nodes

    @property
    def completed_count(self) -> int:
        return sum(1 for n in self._nodes.values() if n.status == "completed")

    @property
    def failed_count(self) -> int:
        return sum(1 for n in self._nodes.values() if n.status == "failed")

    @property
    def pending_count(self) -> int:
        return sum(1 for n in self._nodes.values() if n.status == "pending")

    def progress(self) -> float:
        if not self._nodes:
            return 0.0
        return self.completed_count / len(self._nodes)
