"""
Deprecated — use core.planner.executor or core.planner.state_machine instead.

This legacy planner creates a fixed 3-node DAG (create_directory → write_file →
run_command). New code should use the canonical core.planner package with
templates, state machine, and agent routing.
"""
from __future__ import annotations

import json
import logging
import warnings

from brain.reasoning_engine import reasoning_engine
from core.planner.dag import TaskGraph

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
        self._engine = reasoning_engine

    async def plan(self, goal: str, context: str = "") -> TaskGraph:
        graph = TaskGraph()
        root = graph.add_node(label="create_directory", description="Create project directory structure")
        write = graph.add_node(label="write_file", description="Write source files", depends_on=[root.label])
        build = graph.add_node(label="run_command", description="Build and verify", depends_on=[write.label])
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


planner = Planner()
