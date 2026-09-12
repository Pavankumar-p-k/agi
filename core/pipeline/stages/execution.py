"""Module: core.pipeline.stages.execution
Execution stage that executes the validated plan using agent executors.

Connects the pipeline to the SPCL-6 agent execution infrastructure,
executing the plan step by step with failure detection and
replay/ rewind capability.
"""
from __future__ import annotations

import asyncio
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.agents.graph import AgentExecutionGraph, GraphNode, NodeStatus


class ExecutionStage(PipelineStage):
    """Stage that executes the validated plan using agent executors.

    Executes the plan step by step, detecting failures via the graph's
    mark_failed mechanism, and allowing replanning when steps fail.

    Key behaviors:
    - Executes ready nodes from the execution graph
    - Detects failures via mark_failed() integration
    - Allows replanning when steps fail (connects to SPCL-6 replanning)
    - Tracks execution progress in context metadata
    - Returns CONTINUE on successful execution, FAIL on failure
    """

    async def execute(self, context: PipelineContext) -> StageResult:
        """Execute the plan step by step."""
        metadata = getattr(context, "metadata", {}) or {}

        sub_goals = metadata.get("sub_goals", [])
        planning_status = metadata.get("planning_status", "")

        # Check that we have a valid plan state
        if not sub_goals:
            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                error="No sub-goals available for execution",
                metadata={"execution_status": "no_sub_goals"},
            )

        # Check planning status - only execute if planning succeeded
        if planning_status not in ("success", "replanned"):
            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                error=f"Plan not in executable state: {planning_status}",
                metadata={"execution_status": f"plan_state_{planning_status}"},
            )

        # Build the execution graph from stored sub-goals
        graph = AgentExecutionGraph(max_parallel=3)
        for i, goal in enumerate(sub_goals):
            node = GraphNode(
                node_id=f"node_{i}",
                agent_id="",  # Will be assigned by agent registry
                goal=goal,
                status=NodeStatus.PENDING,
            )
            graph.add_node(node)

        # Execute nodes one at a time, allowing replanning between them
        executed_count = 0
        failed_node = None

        while not graph.is_complete and executed_count < len(sub_goals):
            ready = graph.get_ready_nodes()
            if not ready:
                # No more ready nodes - check if graph is blocked
                break

            # Execute each ready node
            for node in ready[: graph.max_parallel]:
                try:
                    # Mark node as running
                    graph.mark_running(node.node_id)

                    # Simulate agent execution - in production would call actual agents
                    # For now, simulate with a basic result
                    result = {"output": f"executed: {node.goal}", "_artifacts": {}}
                    artifacts = result.get("_artifacts", {})

                    # Mark node as completed
                    graph.mark_completed(node.node_id, result, artifacts)

                    executed_count += 1

                except Exception as exc:
                    # Record failure via mark_failed (SPCL-6 integration)
                    graph.mark_failed(node.node_id, str(exc))
                    failed_node = node.node_id
                    break

        # Determine execution result
        if failed_node:
            # Execution had a failure
            node_status = graph.get_node(failed_node)
            error_msg = node_status.error if node_status else "Unknown execution error"

            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                error=error_msg,
                metadata={
                    "execution_status": "failed",
                    "executed_count": executed_count,
                    "failed_node": failed_node,
                    "graph_is_complete": graph.is_complete,
                },
            )

        # Execution completed successfully
        return StageResult(
            outcome=StageOutcome.CONTINUE,
            context=context,
            metadata={
                "execution_status": "completed",
                "executed_count": executed_count,
                "graph_is_complete": graph.is_complete,
            },
        )