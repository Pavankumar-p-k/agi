"""Distributed graph domain model for cross-worker DAG execution.

A ``DistributedGraph`` is a DAG of ``GraphNode``\ s connected by ``GraphEdge``\ s.
Each node wraps a computation (a ``Request``) that is dispatched to a worker.
Dependencies are resolved before a node becomes eligible for execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

from core.pipeline.messages import Request


class NodeStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()
    SKIPPED = auto()


class GraphState(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()
    PAUSED = auto()


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphNode:
    id: str
    request: Request
    status: NodeStatus = NodeStatus.PENDING
    worker_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)
    affinity_hint: str | None = None


@dataclass
class DistributedGraph:
    id: str
    nodes: dict[str, GraphNode]
    edges: list[GraphEdge]
    state: GraphState = GraphState.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    tenant_id: str = "__system__"
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node
        self.updated_at = datetime.now()

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)
        self.updated_at = datetime.now()

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def get_ready_nodes(self) -> list[GraphNode]:
        ready: list[GraphNode] = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            deps = [e for e in self.edges if e.target_id == node.id]
            if not deps:
                ready.append(node)
                continue
            all_met = all(
                self.nodes[e.source_id].status == NodeStatus.COMPLETED
                for e in deps
                if e.source_id in self.nodes
            )
            if all_met:
                ready.append(node)
        return ready

    def get_downstream_nodes(self, node_id: str) -> list[GraphNode]:
        downstream: list[GraphNode] = []
        for edge in self.edges:
            if edge.source_id == node_id and edge.target_id in self.nodes:
                downstream.append(self.nodes[edge.target_id])
        return downstream

    def has_unfinished(self) -> bool:
        return any(
            n.status in (NodeStatus.PENDING, NodeStatus.RUNNING)
            for n in self.nodes.values()
        )

    def is_terminal(self) -> bool:
        return self.state in (GraphState.COMPLETED, GraphState.FAILED, GraphState.CANCELLED)

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "graph_id": self.id,
            "state": self.state.name,
            "nodes": [
                {
                    "id": n.id,
                    "status": n.status.name,
                    "worker_id": n.worker_id,
                    "error": n.error,
                    "started_at": n.started_at.isoformat() if n.started_at else None,
                    "completed_at": n.completed_at.isoformat() if n.completed_at else None,
                    "retry_count": n.retry_count,
                    "max_retries": n.max_retries,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {"source_id": e.source_id, "target_id": e.target_id}
                for e in self.edges
            ],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tenant_id": self.tenant_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_snapshot(cls, data: dict[str, Any], nodes: dict[str, GraphNode]) -> DistributedGraph:
        edges = [
            GraphEdge(source_id=e["source_id"], target_id=e["target_id"])
            for e in data.get("edges", [])
        ]
        for nd in data.get("nodes", []):
            nid = nd["id"]
            if nid in nodes:
                nodes[nid].status = NodeStatus[nd["status"]]
                nodes[nid].worker_id = nd.get("worker_id")
                nodes[nid].error = nd.get("error")
        return cls(
            id=data["graph_id"],
            nodes=nodes,
            edges=edges,
            state=GraphState[data["state"]],
            tenant_id=data.get("tenant_id", "__system__"),
            metadata=data.get("metadata", {}),
        )
