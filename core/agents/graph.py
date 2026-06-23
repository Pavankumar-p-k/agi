"""AgentExecutionGraph — DAG for parallel agent execution.

Each node maps to an agent task. Nodes within the same phase run
concurrently; phases are sequential barriers derived from step_name.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Step name → execution phase (lower = earlier, sequential barrier)
_STEP_PHASE: dict[str, int] = {
    "research": 0,
    "codegen": 1,
    "build": 1,
    "test": 2,
    "security": 3,
    "validate": 3,
    "apk": 4,
    "docs": 4,
    "notify": 5,
    "email": 6,
}


class NodeStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class GraphNode:
    """A single node in the agent execution graph.

    Each node corresponds to one agent execution task.
    Supports dependency edges and artifact handoff for multi-agent coordination.
    """
    node_id: str
    agent_id: str
    goal: str
    phase: int
    depends_on: list[str] = field(default_factory=list)
    input_artifacts: dict[str, str] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    status: NodeStatus = NodeStatus.PENDING
    result: dict[str, Any] | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is not None and self.completed_at is not None:
            return self.completed_at - self.started_at
        return None


def get_phase_for_step(step_name: str) -> int:
    """Return the execution phase for a step name."""
    return _STEP_PHASE.get(step_name, 50)


def build_graph_from_tasks(
    tasks: list[dict],
    edges: list[tuple[str, str, dict[str, str]]] | None = None,
) -> AgentExecutionGraph:
    """Build an AgentExecutionGraph from a list of agent router tasks.

    Each task dict has: agent_id, goal, step, parameters.
    Nodes are grouped into phases based on their step name.

    Optional edges parameter establishes dependency chains for artifact handoff.
    Each edge is (from_node_id, to_node_id, input_artifact_map) where
    input_artifact_map maps upstream artifact keys to downstream parameter keys.
    """
    graph = AgentExecutionGraph()
    for i, task in enumerate(tasks):
        step_name = task.get("step", task["agent_id"])
        phase = get_phase_for_step(step_name)
        node = GraphNode(
            node_id=f"n_{i}",
            agent_id=task["agent_id"],
            goal=task.get("goal", step_name),
            phase=phase,
            parameters=dict(task.get("parameters", {})),
        )
        graph.add_node(node)

    if edges:
        edge_map: dict[str, list[tuple[str, dict[str, str]]]] = {}
        for from_id, to_id, artifact_map in edges:
            if to_id not in edge_map:
                edge_map[to_id] = []
            edge_map[to_id].append((from_id, artifact_map))

        for to_id, deps in edge_map.items():
            node = graph.nodes.get(to_id)
            if node:
                node.depends_on = [dep[0] for dep in deps]
                merged: dict[str, str] = {}
                for _, amap in deps:
                    merged.update(amap)
                node.input_artifacts = merged

    return graph


class AgentExecutionGraph:
    """Directed acyclic graph of agent tasks with phase-based barriers.

    Supports:
      - Phase-based sequential barriers (all phase N complete → phase N+1)
      - Tracking completion, failures, artifacts
      - Serialization for crash recovery
    """

    def __init__(self, max_parallel: int = 5):
        self.nodes: dict[str, GraphNode] = {}
        self.max_parallel = max_parallel
        self._phase_order: list[int] = []
        self._phase_nodes: dict[int, list[str]] = {}

    def has_unmet_dependencies(self, node_id: str) -> bool:
        """Return True if any dependency of node_id is not COMPLETED."""
        node = self.nodes.get(node_id)
        if not node or not node.depends_on:
            return False
        for dep_id in node.depends_on:
            dep = self.nodes.get(dep_id)
            if not dep or dep.status != NodeStatus.COMPLETED:
                return True
        return False

    def add_node(self, node: GraphNode) -> str:
        self.nodes[node.node_id] = node
        if node.phase not in self._phase_nodes:
            self._phase_nodes[node.phase] = []
            self._phase_order = sorted(self._phase_nodes.keys())
        self._phase_nodes[node.phase].append(node.node_id)
        return node.node_id

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def get_ready_nodes(self) -> list[GraphNode]:
        """Return nodes whose phase barrier is met and all dependencies are completed."""
        for phase in self._phase_order:
            phase_nodes = [
                self.nodes[nid]
                for nid in self._phase_nodes.get(phase, [])
            ]
            if not phase_nodes:
                continue

            # If not phase 0, check all prior phases are terminal (phase barrier)
            if phase > 0:
                prior_phases = [p for p in self._phase_order if p < phase]
                all_prior_terminal = all(
                    all(
                        self.nodes[nid].status in (NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED)
                        for nid in self._phase_nodes.get(p, [])
                    )
                    for p in prior_phases
                )
                if not all_prior_terminal:
                    continue

            # Within this phase, find pending nodes whose dependencies are met
            pending = [
                n for n in phase_nodes
                if n.status == NodeStatus.PENDING
                and not self.has_unmet_dependencies(n.node_id)
            ]
            if pending:
                return pending

            # All completed/failed/skipped/waiting — move to next phase
            all_terminal = all(
                n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED)
                for n in phase_nodes
            )
            if all_terminal:
                continue
            return []
        return []

    def mark_running(self, node_id: str) -> None:
        node = self.nodes.get(node_id)
        if node:
            node.status = NodeStatus.RUNNING
            node.started_at = time.monotonic()

    def mark_completed(self, node_id: str, result: dict,
                       artifacts: dict[str, str] | None = None) -> None:
        node = self.nodes.get(node_id)
        if not node:
            return
        node.status = NodeStatus.COMPLETED
        node.result = result
        node.completed_at = time.monotonic()
        if artifacts:
            node.artifacts.update(artifacts)

    def mark_failed(self, node_id: str, error: str) -> None:
        node = self.nodes.get(node_id)
        if not node:
            return
        node.status = NodeStatus.FAILED
        node.error = error
        node.completed_at = time.monotonic()

    def mark_skipped(self, node_id: str, reason: str = "") -> None:
        node = self.nodes.get(node_id)
        if not node:
            return
        node.status = NodeStatus.SKIPPED
        node.error = reason
        node.completed_at = time.monotonic()

    @property
    def is_complete(self) -> bool:
        if not self.nodes:
            return True
        return all(
            n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED)
            for n in self.nodes.values()
        )

    @property
    def is_blocked(self) -> bool:
        """True if no node can make progress (pending nodes depend on failed phases)."""
        if self.is_complete:
            return False
        # Check if any node completed — without any completion, there's nothing to block
        if not any(n.status == NodeStatus.COMPLETED for n in self.nodes.values()):
            # If all nodes in phase 0 failed, we're blocked
            p0 = [self.nodes[nid] for nid in self._phase_nodes.get(0, [])]
            if p0 and all(n.status == NodeStatus.FAILED for n in p0):
                return True
            return False
        # Check if any pending phase has all-prior-phases terminal with failures
        for phase in self._phase_order:
            phase_nodes = [
                self.nodes[nid]
                for nid in self._phase_nodes.get(phase, [])
            ]
            pending = [n for n in phase_nodes if n.status == NodeStatus.PENDING]
            if not pending:
                continue
            prior_phases = [p for p in self._phase_order if p < phase]
            if not prior_phases:
                continue
            # All prior phases must be terminal
            all_terminal = all(
                all(
                    self.nodes[nid].status in (NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED)
                    for nid in self._phase_nodes.get(p, [])
                )
                for p in prior_phases
            )
            if all_terminal:
                # Prior phases are done but none completed — blocked
                prior_any_completed = any(
                    any(
                        self.nodes[nid].status == NodeStatus.COMPLETED
                        for nid in self._phase_nodes.get(p, [])
                    )
                    for p in prior_phases
                )
                if not prior_any_completed:
                    return True
        return False

    def get_all_artifacts(self) -> dict[str, str]:
        """Merge artifacts from all completed nodes."""
        merged: dict[str, str] = {}
        for node in self.nodes.values():
            if node.status == NodeStatus.COMPLETED:
                merged.update(node.artifacts)
        return merged

    def get_all_errors(self) -> list[str]:
        """Collect errors from all failed nodes."""
        return [
            f"{n.node_id}({n.agent_id}): {n.error}"
            for n in self.nodes.values()
            if n.status == NodeStatus.FAILED and n.error
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize for crash recovery."""
        return {
            "max_parallel": self.max_parallel,
            "phase_order": list(self._phase_order),
            "phase_nodes": {str(k): list(v) for k, v in self._phase_nodes.items()},
            "nodes": {
                nid: {
                    "node_id": n.node_id,
                    "agent_id": n.agent_id,
                    "goal": n.goal,
                    "phase": n.phase,
                    "depends_on": list(n.depends_on),
                    "input_artifacts": dict(n.input_artifacts),
                    "parameters": dict(n.parameters),
                    "status": n.status.value,
                    "result": n.result,
                    "artifacts": dict(n.artifacts),
                    "error": n.error,
                    "started_at": n.started_at,
                    "completed_at": n.completed_at,
                }
                for nid, n in self.nodes.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentExecutionGraph:
        graph = cls(max_parallel=data.get("max_parallel", 5))
        for nid, ndata in data.get("nodes", {}).items():
            node = GraphNode(
                node_id=ndata["node_id"],
                agent_id=ndata["agent_id"],
                goal=ndata["goal"],
                phase=ndata["phase"],
                depends_on=list(ndata.get("depends_on", [])),
                input_artifacts=dict(ndata.get("input_artifacts", {})),
                parameters=dict(ndata.get("parameters", {})),
                status=NodeStatus(ndata.get("status", "pending")),
                result=ndata.get("result"),
                artifacts=dict(ndata.get("artifacts", {})),
                error=ndata.get("error"),
                started_at=ndata.get("started_at"),
                completed_at=ndata.get("completed_at"),
            )
            graph.nodes[nid] = node
        graph._phase_order = data.get("phase_order", [])
        graph._phase_nodes = {
            int(k): list(v)
            for k, v in data.get("phase_nodes", {}).items()
        }
        return graph
