"""AgentExecutionGraph — phase-b DAG of agent tasks with parallel execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# Step name -> execution phase (barrier: phase N waits for all of N-1).
_STEP_PHASES: dict[str, int] = {
    "research": 0,
    "plan": 0,
    "understand": 0,
    "build": 1,
    "implement": 1,
    "codegen": 1,
    "test": 2,
    "verify": 2,
    "package": 3,
    "deploy": 4,
    "email": 6,
    "notify": 6,
}

_UNKNOWN_PHASE = 50


def get_phase_for_step(step: str) -> int:
    return _STEP_PHASES.get((step or "").lower(), _UNKNOWN_PHASE)


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
    phase: int = 0
    parameters: dict[str, Any] = field(default_factory=dict)
    status: NodeStatus = NodeStatus.PENDING
    error: Optional[str] = None
    output: Optional[dict[str, Any]] = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def duration(self) -> Optional[float]:
        if self.started_at is None or self.completed_at is None:
            return None
        return self.completed_at - self.started_at


@dataclass
class AgentExecutionGraph:
    max_parallel: int = 5
    nodes: dict[str, GraphNode] = field(default_factory=dict)

    # ── structure ────────────────────────────────────────────────────
    def add_node(self, node: GraphNode) -> GraphNode:
        self.nodes[node.node_id] = node
        return node

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self.nodes.get(node_id)

    # ── readiness / barriers ────────────────────────────────────────
    def _phase_done(self, phase: int) -> bool:
        return all(
            n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED)
            for n in self.nodes.values() if n.phase == phase
        )

    def get_ready_nodes(self) -> list[GraphNode]:
        """Pending nodes of the first non-terminal phase (phase barrier)."""
        if not self.nodes:
            return []
        phases = sorted({n.phase for n in self.nodes.values()})
        for phase in phases:
            phase_nodes = [n for n in self.nodes.values() if n.phase == phase]
            all_terminal = all(
                n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED)
                for n in phase_nodes
            )
            if all_terminal:
                continue  # phase finished — next phase may open
            return [n for n in phase_nodes if n.status == NodeStatus.PENDING]
        return []

    @property
    def is_blocked(self) -> bool:
        """True when every earlier phase is terminal but nothing can proceed
        because a prior phase failed entirely."""
        if not self.nodes or self.is_complete:
            return False
        phases = sorted({n.phase for n in self.nodes.values()})
        for i, phase in enumerate(phases):
            phase_nodes = [n for n in self.nodes.values() if n.phase == phase]
            all_terminal = all(
                n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED)
                for n in phase_nodes
            )
            if not all_terminal:
                return False
            if all(n.status == NodeStatus.FAILED for n in phase_nodes):
                # This phase fully failed — later pending phases are blocked.
                later = [n for n in self.nodes.values() if n.phase > phase]
                return any(n.status == NodeStatus.PENDING for n in later)
        return False

    @property
    def is_complete(self) -> bool:
        return all(
            n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED)
            for n in self.nodes.values()
        )

    # ── state transitions ───────────────────────────────────────────
    def mark_running(self, node_id: str) -> None:
        import time
        node = self.nodes[node_id]
        node.status = NodeStatus.RUNNING
        node.started_at = time.monotonic()

    def mark_completed(self, node_id: str, output: Optional[dict] = None,
                       artifacts: Optional[dict] = None) -> None:
        import time
        node = self.nodes[node_id]
        node.status = NodeStatus.COMPLETED
        node.completed_at = time.monotonic()
        node.output = output or {}
        if artifacts:
            node.artifacts.update(artifacts)

    def mark_failed(self, node_id: str, error: str) -> None:
        import time
        node = self.nodes[node_id]
        node.status = NodeStatus.FAILED
        node.completed_at = time.monotonic()
        node.error = error

    # ── aggregation ─────────────────────────────────────────────────
    def get_all_artifacts(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for node in self.nodes.values():
            merged.update(node.artifacts)
        return merged

    # ── serialization ───────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "max_parallel": self.max_parallel,
            "nodes": {
                nid: {
                    "node_id": n.node_id, "agent_id": n.agent_id, "goal": n.goal,
                    "phase": n.phase, "status": n.status.value,
                    "error": n.error, "output": n.output,
                    "artifacts": n.artifacts, "parameters": n.parameters,
                    "started_at": n.started_at, "completed_at": n.completed_at,
                }
                for nid, n in self.nodes.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentExecutionGraph":
        graph = cls(max_parallel=int(data.get("max_parallel", 5)))
        for nid, nd in (data.get("nodes") or {}).items():
            graph.nodes[nid] = GraphNode(
                node_id=nd["node_id"], agent_id=nd["agent_id"], goal=nd["goal"],
                phase=int(nd.get("phase", 0)),
                status=NodeStatus(nd.get("status", "pending")),
                error=nd.get("error"), output=nd.get("output"),
                artifacts=dict(nd.get("artifacts") or {}),
                parameters=dict(nd.get("parameters") or {}),
                started_at=nd.get("started_at"), completed_at=nd.get("completed_at"),
            )
        return graph


def build_graph_from_tasks(tasks: list[dict[str, Any]]) -> AgentExecutionGraph:
    """tasks: [{'agent_id', 'goal', 'step', 'parameters'}] -> phase DAG."""
    graph = AgentExecutionGraph()
    for i, t in enumerate(tasks or []):
        step = str(t.get("step", ""))
        graph.add_node(GraphNode(
            node_id=t.get("node_id") or f"node_{i}",
            agent_id=str(t.get("agent_id", "")),
            goal=str(t.get("goal", "")),
            phase=get_phase_for_step(step),
            parameters=dict(t.get("parameters") or {}),
        ))
    return graph
