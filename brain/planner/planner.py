"""
Deprecated — use core.planner instead.

Shim that wraps CorePlanner (GoalDecomposer + PlannerExecutor) in the old
brain.planner.Planner interface. All new code should import from core.planner.
"""
from __future__ import annotations

import json
import logging
import warnings

from core.planner.dag import TaskGraph
from core.planner.decomposer import GoalDecomposer
from core.planner.executor import PlannerExecutor
from core.planner.protocol import Plan, PlanStatus

logger = logging.getLogger(__name__)

_deprecation_warned = False


def _warn():
    global _deprecation_warned
    if not _deprecation_warned:
        warnings.warn(
            "brain.planner.Planner is deprecated. Use 'core.planner' instead.",
            DeprecationWarning, stacklevel=2,
        )
        _deprecation_warned = True


class Planner:
    def __init__(self):
        _warn()
        self._decomposer = GoalDecomposer()
        self._executor = PlannerExecutor()

    async def plan(self, goal: str, context: str = "") -> TaskGraph:
        subgoal = self._decomposer.decompose(goal)
        graph = TaskGraph()
        for leaf in subgoal.flatten():
            graph.add_node(
                label=leaf.step_name or "build",
                description=leaf.description,
            )
        if len(graph) == 0:
            graph.add_node(label="build", description=goal[:80])
        logger.info("[Planner] created %d-node task graph for: %s", len(graph), goal[:60])
        return graph

    async def replan(self, graph: TaskGraph, failed_node_id: str,
                     error_context: str = "") -> TaskGraph:
        failed_node = graph.get_node(failed_node_id)
        if not failed_node:
            return graph
        logger.info("[Planner] replanning after failure of %s", failed_node.label)
        plan_context = (
            f"Task '{failed_node.label}' failed with error: {error_context}\n"
            f"Existing task graph: {json.dumps(graph.to_dict(), indent=2)}\n"
            "Replan this task or find an alternative approach."
        )
        new_graph = await self.plan(
            f"Alternative approach for: {failed_node.description or failed_node.label}",
            plan_context,
        )
        if len(new_graph) > 0:
            graph.remove_node(failed_node_id)
            for new_node in new_graph.nodes.values():
                new_node.depends_on = [
                    d for d in new_node.depends_on
                    if d in graph.nodes
                ]
                graph.nodes[new_node.id] = new_node
        return graph

    def create_plan(self, goal: str, context: dict | None = None) -> Plan:
        """CorePlanner protocol compatibility."""
        subgoal = self._decomposer.decompose(goal)
        plan = self._executor.create_plan(goal)
        return Plan(
            id=plan.get("plan_id", goal[:8]) if plan else goal[:8],
            goal=goal,
            status=PlanStatus.DRAFT,
            root_node={"id": "root", "children": [s.to_dict() if hasattr(s, 'to_dict') else {"id": s.id, "description": s.description} for s in subgoal.flatten()]},
        )


planner = Planner()
