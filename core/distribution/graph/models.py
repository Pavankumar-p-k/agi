"""Distributed graph domain model.

``DistributedGraph`` is a dependency-aware DAG of :class:`GraphNode`s. All
dependency resolution is local — no worker state is consulted (Rule 44) — and
snapshots are plain JSON-serialisable dicts (Rule 45).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional


class NodeStatus(str, Enum):
    """Lifecycle of a single graph node."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return str(self.value)


class GraphState(str, Enum):
    """Lifecycle of a whole graph."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return str(self.value)


TERMINAL_NODE_STATUSES = (NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.CANCELLED)
TERMINAL_GRAPH_STATES = (GraphState.COMPLETED, GraphState.FAILED, GraphState.CANCELLED)


def _serialize_request(request: Any) -> Any:
    if request is None:
        return None
    if isinstance(request, dict):
        return dict(request)
    payload = {}
    for attr in ("text", "transport", "user_id", "session_id"):
        if hasattr(request, attr):
            payload[attr] = getattr(request, attr)
    return payload or str(request)


@dataclass
class GraphNode:
    """A single unit of work in the graph."""

    id: str
    request: Any = None
    status: NodeStatus = NodeStatus.PENDING
    worker_id: Optional[str] = None
    affinity_hint: Optional[str] = None
    max_retries: int = 0
    attempts: int = 0
    result: Any = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id or "").strip()
        if not self.id:
            raise ValueError("GraphNode.id is required")
        if not isinstance(self.status, NodeStatus):
            self.status = NodeStatus(str(self.status))

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_NODE_STATUSES

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status.value,
            "worker_id": self.worker_id,
            "request": _serialize_request(self.request),
            "attempts": self.attempts,
            "error": self.error,
        }


@dataclass(frozen=True)
class GraphEdge:
    """A directed dependency: ``source`` must finish before ``target`` starts."""

    source: str
    target: str

    def __iter__(self):
        yield self.source
        yield self.target

    def to_dict(self) -> dict:
        return {"source": self.source, "target": self.target}


@dataclass
class DistributedGraph:
    """A dependency-aware DAG of nodes."""

    id: str
    nodes: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)
    state: GraphState = GraphState.PENDING
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.nodes = {str(k): v for k, v in dict(self.nodes or {}).items()}
        self.edges = [
            e if isinstance(e, GraphEdge) else GraphEdge(str(e[0]), str(e[1]))
            for e in (self.edges or [])
        ]
        if not isinstance(self.state, GraphState):
            self.state = GraphState(str(self.state))

    # ── mutation ────────────────────────────────────────────────────
    def add_node(self, node: GraphNode) -> GraphNode:
        if not isinstance(node, GraphNode):
            raise TypeError("add_node() expects a GraphNode")
        self.nodes[node.id] = node
        return node

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self.nodes.get(str(node_id))

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        if not isinstance(edge, GraphEdge):
            edge = GraphEdge(str(edge[0]), str(edge[1]))
        if edge not in self.edges:
            self.edges.append(edge)
        return edge

    # ── dependency resolution (local only) ──────────────────────────
    def get_dependencies(self, node_id: str) -> list:
        """Direct upstream nodes of *node_id*."""
        return [self.nodes[e.source] for e in self.edges
                if e.target == str(node_id) and e.source in self.nodes]

    def get_downstream_nodes(self, node_id: str) -> list:
        """All nodes reachable downstream of *node_id* (transitive)."""
        seen: list = []
        queue = [str(node_id)]
        visited = {str(node_id)}
        while queue:
            current = queue.pop(0)
            for edge in self.edges:
                if edge.source != current or edge.target in visited:
                    continue
                target = self.nodes.get(edge.target)
                if target is None:
                    continue
                visited.add(edge.target)
                seen.append(target)
                queue.append(edge.target)
        return seen

    def get_ready_nodes(self) -> list:
        """PENDING nodes whose every dependency has COMPLETED."""
        ready = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            deps = self.get_dependencies(node.id)
            if all(dep.status == NodeStatus.COMPLETED for dep in deps):
                ready.append(node)
        return ready

    def has_unfinished(self) -> bool:
        return any(not node.is_terminal for node in self.nodes.values())

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_GRAPH_STATES

    # ── snapshots ───────────────────────────────────────────────────
    def to_snapshot(self) -> dict:
        """JSON-serialisable immutable snapshot of the graph (Rule 45)."""
        return {
            "graph_id": self.id,
            "state": self.state.value,
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict, original_nodes: Optional[dict] = None) -> "DistributedGraph":
        """Rebuild a graph from a snapshot plus the caller's node objects."""
        snapshot = dict(snapshot or {})
        graph_id = snapshot.get("graph_id", "")
        originals = dict(original_nodes or {})
        nodes: dict = {}
        for entry in snapshot.get("nodes", []) or []:
            if not isinstance(entry, dict):
                continue
            node_id = str(entry.get("id", ""))
            node = originals.get(node_id)
            if node is None:
                node = GraphNode(id=node_id, request=entry.get("request"))
            node.status = NodeStatus(str(entry.get("status", NodeStatus.PENDING.value)))
            node.worker_id = entry.get("worker_id", node.worker_id)
            node.attempts = entry.get("attempts", node.attempts)
            node.error = entry.get("error", None)
            nodes[node_id] = node
        edges = []
        for entry in snapshot.get("edges", []) or []:
            if isinstance(entry, dict):
                edges.append(GraphEdge(str(entry.get("source")), str(entry.get("target"))))
            elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                edges.append(GraphEdge(str(entry[0]), str(entry[1])))
        state = GraphState(str(snapshot.get("state", GraphState.PENDING.value)))
        return cls(id=graph_id, nodes=nodes, edges=edges, state=state)


__all__ = [
    "NodeStatus", "GraphState", "GraphNode", "GraphEdge", "DistributedGraph",
    "TERMINAL_NODE_STATUSES", "TERMINAL_GRAPH_STATES",
]
