from __future__ import annotations

import json
import logging

from brain.reasoning_engine import reasoning_engine

from .task_graph import TaskGraph

logger = logging.getLogger(__name__)


class Planner:
    """Breaks goals into DAG-based task graphs.

    Uses a fixed generic plan structure (create_directory -> write_file -> run_command)
    since the LLM is unreliable for structured JSON output.
    """

    def __init__(self):
        self._engine = reasoning_engine

    async def plan(self, goal: str, context: str = "") -> TaskGraph:
        """Produce a DAG of tasks for any goal."""
        graph = TaskGraph()

        root = graph.add_node(label="create_directory", description="Create project directory structure")
        write = graph.add_node(label="write_file", description="Write source files", depends_on=[root.label])
        build = graph.add_node(label="run_command", description="Build and verify", depends_on=[write.label])

        logger.info("[Planner] created %d-node task graph for: %s", len(graph), goal[:60])
        return graph

    async def replan(self, graph: TaskGraph, failed_node_id: str,
                     error_context: str = "") -> TaskGraph:
        """Replan around a failed task node."""
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
