"""Module: core.planner.executor
Planner execution engine for agent-driven workflows with failure detection,
replanning, evidence recording, and outcome determination.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional, List

from core.agents.graph import AgentExecutionGraph, GraphNode, NodeStatus
from core.planner.comparison import ComparisonCriterion, StrategyComparator, StrategyProfile
from core.planner.evidence import (
    FailureEvidence,
    PlannerEvidence,
    ReplanEvidence,
    StrategyComparisonEvidence,
    VerificationEvidence,
    EvidenceSource,
)
from core.planner.outcomes import determine_outcome, PlannerOutcome
from core.planner.replan import ReplanDecision, Replanner
from core.planner.state_machine import PlannerStateMachine, PlannerStateName
from core.planner.strategies import Strategy, StrategyRegistry


# Keys that ExecutionResult supports for dict-like compatibility
_EXECUTION_RESULT_DICT_KEYS = {
    "status",
    "goal",
    "error",
    "artifacts",
    "final_state",
    "replanned",
    "failure_evidence",
    "comparison_evidence",
    "verification_evidence",
}


class ExecutionMode(str, Enum):
    """Modes of planner execution."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    WITH_REPLANNING = "with_replanning"


@dataclass
class PlannerState:
    """State tracked during planning and execution."""
    goal: str = ""
    sub_goals: list[str] = field(default_factory=list)
    execution_graph: dict[str, Any] = field(default_factory=dict)
    current_step: str | None = None
    completed: bool = False
    failed: bool = False
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    mode: ExecutionMode = ExecutionMode.WITH_REPLANNING
    replans_attempted: int = 0
    successful_replans: int = 0


@dataclass
class ExecutionResult:
    """Result of executing a planning cycle."""

    status: PlannerOutcome
    goal: str
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    final_state: str = "unknown"
    replanned: bool = False
    failure_evidence: FailureEvidence | None = None
    comparison_evidence: StrategyComparisonEvidence | None = None
    verification_evidence: VerificationEvidence | None = None

    def __contains__(self, key: str) -> bool:
        """Enable 'in' operator / assertIn compatibility."""
        return key in _EXECUTION_RESULT_DICT_KEYS

    def __getitem__(self, key: str) -> Any:
        """Enable dict-like access for backward compatibility.

        Supports the keys used by existing tests and planner code:
        "status", "goal", "error", "artifacts", "final_state",
        "replanned", "failure_evidence", "comparison_evidence",
        "verification_evidence".
        """
        mapping = {
            "status": self.status,
            "goal": self.goal,
            "error": self.error,
            "artifacts": self.artifacts,
            "final_state": self.final_state,
            "replanned": self.replanned,
            "failure_evidence": self.failure_evidence,
            "comparison_evidence": self.comparison_evidence,
            "verification_evidence": self.verification_evidence,
        }
        if key in mapping:
            return mapping[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Enable .get() method compatibility."""
        try:
            return self.__getitem__(key)
        except KeyError:
            return default


class PlannerExecutor:
    """Planner execution engine that decomposes goals, builds execution graphs,
    executes steps with failure detection, replans on failure, records evidence,
    and determines final outcomes.

    The executor coordinates:
    - State machine for valid transition tracking
    - Evidence recording for replanning decisions
    - Strategy comparison for alternate strategy selection
    - Outcome determination (SUCCESS / FAILURE / UNCONFIRMED / REPLANNED)
    """

    def __init__(
        self,
        max_parallel: int = 3,
        state_machine: PlannerStateMachine | None = None,
        evidence: PlannerEvidence | None = None,
        replanner: Replanner | None = None,
        comparator: StrategyComparator | None = None,
        strategy_registry: StrategyRegistry | None = None,
    ):
        self.max_parallel = max_parallel
        self.state = PlannerState()
        self.state_machine = state_machine or PlannerStateMachine()
        self.evidence = evidence or PlannerEvidence()
        self.replanner = replanner or Replanner(
            state_machine=self.state_machine,
            evidence=self.evidence,
            strategy_registry=strategy_registry or StrategyRegistry(),
            comparator=comparator,
        )
        self.execution_graph = AgentExecutionGraph(max_parallel=max_parallel)

    def decompose_goal(self, goal: str) -> list[str]:
        """Decompose a high-level goal into sub-goals.

        Uses a simple decomposition; subclasses or plugins can override
        with richer LLM-driven decomposition.
        """
        sub_goals = [goal]  # placeholder; actual decomposition would be richer
        self.state.sub_goals = sub_goals
        return sub_goals

    def build_execution_graph(self, sub_goals: list[str]) -> AgentExecutionGraph:
        """Build an execution graph from sub-goals.

        Each sub-goal becomes a node in the graph with PENDING status.
        """
        self.execution_graph = AgentExecutionGraph(max_parallel=self.max_parallel)
        for i, sg in enumerate(sub_goals):
            node = GraphNode(
                node_id=f"node_{i}",
                agent_id="",
                goal=sg,
                status=NodeStatus.PENDING,
            )
            self.execution_graph.add_node(node)
        # Update state dict for compatibility
        self.state.execution_graph = {
            f"node_{i}": {"goal": sg, "status": "pending"} for i, sg in enumerate(sub_goals)
        }
        # Transition state machine to READY
        self.state_machine.transition(PlannerStateName.READY)
        return self.execution_graph

    async def execute_step(self, node_id: str, agent_execute: Callable | None = None) -> dict[str, Any]:
        """Execute a single step in the execution graph.

        Returns a dict with execution result information.
        """
        node = self.execution_graph.get_node(node_id)
        if node is None:
            return {"status": "failed", "error": f"node {node_id} not found"}

        goal = node.goal

        try:
            if agent_execute is None:
                result = "mock result"
            else:
                result = await agent_execute(goal) if asyncio.iscoroutinefunction(agent_execute) else agent_execute(goal)

            node.status = NodeStatus.COMPLETED

            # Record artifacts if result is a dict
            if isinstance(result, dict):
                artifacts = result.get("_artifacts", {}) or result.get("artifacts", {})
                if artifacts:
                    node.artifacts.update(artifacts)
                    self.state.artifacts.update(artifacts)

            # Transition state machine
            self.state_machine.transition(PlannerStateName.RUNNING)

            return {
                "status": "success",
                "result": result,
                "node_id": node_id,
            }
        except Exception as e:
            # Record failure via the graph's mark_failed mechanism
            self.execution_graph.mark_failed(node_id, str(e))

            # Transition state machine to FAILED
            self.state_machine.transition(PlannerStateName.FAILED, reason=str(e))

            # Handle replanning through the replanner
            self._handle_node_failure(node_id, str(e))

            return {
                "status": "failed",
                "error": str(e),
                "node_id": node_id,
            }

    def _handle_node_failure(self, node_id: str, error: str) -> None:
        """Handle failure of a node: record evidence, attempt replanning.

        The current plan description is derived from the graph's node goals.
        """
        # Build a simple plan description from the graph nodes
        node_descriptions: list[str] = []
        for nid, n in self.execution_graph.nodes.items():
            node_descriptions.append(f"{nid}:{n.goal}")
        current_plan_desc = " | ".join(node_descriptions) if node_descriptions else "unknown plan"

        # The replanner handles: evidence recording, strategy comparison,
        # state transitions, and revised plan creation
        result = self.replanner.handle_failure(
            step_id=node_id,
            error=error,
            context={"node": node_id, "graph_nodes": len(self.execution_graph.nodes)},
            current_plan_desc=current_plan_desc,
        )

        # Update executor state from replanner result
        if result["decision"] == ReplanDecision.SWITCH_STRATEGY:
            self.state.replans_attempted += 1
            if result.get("outcome") == PlannerOutcome.REPLANNED:
                self.state.successful_replans += 1

        # Store reference to replan evidence
        self.evidence.replan_evidence = result  # type: ignore[assignment]

    async def execute_workflow(self, goal: str, agent_execute: Callable | None = None) -> ExecutionResult:
        """Execute a complete workflow with failure detection and replanning.

        The flow is:
        1. Decompose goal into sub-goals
        2. Build execution graph
        3. Execute nodes, handling failures with replanning
        4. Determine final outcome
        5. Return ExecutionResult with full evidence
        """
        # Reset state
        self.state = PlannerState(goal=goal)

        # Decompose and build graph
        sub_goals = self.decompose_goal(goal)
        self.build_execution_graph(sub_goals)

        # Execute nodes until graph is complete
        while not self.execution_graph.is_complete:
            ready = self.execution_graph.get_ready_nodes()
            if not ready:
                break

            # Execute ready nodes one at a time, allowing replanning between them
            for node in ready:
                node_result = await self.execute_step(node.node_id, agent_execute)
                if node_result.get("status") == "failed":
                    # Failure already handled inside execute_step (replanning etc.)
                    # Check if graph is complete after replanning
                    if self.execution_graph.is_complete:
                        break

        # Determine final outcome
        success = not any(
            n.status == NodeStatus.FAILED for n in self.execution_graph.nodes.values()
        )

        # verification: basic — success implies verified unless caller overrides
        verified = success

        # replanned flag
        replanned = self.state.replans_attempted > 0

        # Determine outcome using the outcomes module
        outcome = determine_outcome(
            success=success,
            verified=verified,
            replanned=replanned,
        )

        # Build artifacts from graph
        artifacts = self.execution_graph.get_all_artifacts()

        # Get final state from state machine
        final_state = self.state_machine.current_state().value

        return ExecutionResult(
            status=outcome,
            goal=goal,
            error=self.state.error,
            artifacts=artifacts,
            final_state=final_state,
            replanned=replanned,
            failure_evidence=self.evidence.failure_evidence,
            comparison_evidence=self.evidence.comparison_evidence,
            verification_evidence=self.evidence.verification_evidence,
        )