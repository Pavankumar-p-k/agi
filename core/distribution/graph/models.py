from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GraphState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class GraphNode:
    id: str
    request: Any = None
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    error: str | None = None
    affinity_hint: str | None = None
    max_retries: int = 0


@dataclass
class GraphEdge:
    source: str
    target: str

    @property
    def from_node(self):
        return self.source

    @property
    def to_node(self):
        return self.target


@dataclass
class DistributedGraph:
    id: str
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    state: GraphState = GraphState.PENDING

    def add_node(self, node):
        self.nodes[node.id] = node

    def get_node(self, node_id):
        return self.nodes[node_id]

    def add_edge(self, edge):
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise ValueError("graph edge references an unknown node")
        self.edges.append(edge)

    def get_ready_nodes(self):
        completed = {n.id for n in self.nodes.values() if n.status == NodeStatus.COMPLETED}
        result = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            dependencies = [e.source for e in self.edges if e.target == node.id]
            if all(dep in completed for dep in dependencies):
                result.append(node)
        return result

    def get_downstream_nodes(self, node_id):
        return [self.nodes[e.target] for e in self.edges if e.source == node_id]

    def has_unfinished(self):
        return any(n.status not in (NodeStatus.COMPLETED, NodeStatus.CANCELLED) for n in self.nodes.values())

    def is_terminal(self):
        return self.state in (GraphState.COMPLETED, GraphState.FAILED, GraphState.CANCELLED)

    def to_snapshot(self):
        return {
            "graph_id": self.id,
            "state": self.state.value,
            "nodes": [{"id": n.id, "status": n.status.value, "error": n.error} for n in self.nodes.values()],
            "edges": [{"source": e.source, "target": e.target} for e in self.edges],
        }

    @classmethod
    def from_snapshot(cls, snapshot, original_nodes):
        nodes = {}
        for item in snapshot.get("nodes", []):
            node = original_nodes[item["id"]]
            node.status = NodeStatus(item.get("status", NodeStatus.PENDING))
            node.error = item.get("error")
            nodes[node.id] = node
        return cls(snapshot["graph_id"], nodes,
                   [GraphEdge(e["source"], e["target"]) for e in snapshot.get("edges", [])],
                   GraphState(snapshot.get("state", GraphState.PENDING)))
