"""ParallelAgentExecutor — executes a DAG of agent tasks concurrently.

Uses asyncio.TaskGroup (Python 3.11+) to run dependency-free nodes
in parallel within each execution phase. Phases are sequential barriers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from core.agents.events import AgentEvent
from core.agents.graph import AgentExecutionGraph, GraphNode, NodeStatus
from core.agents.router import get_agent
from core.workflow.context import ExecutionContext

logger = logging.getLogger(__name__)


class ParallelAgentExecutor:
    """Executes an AgentExecutionGraph using phase-parallel dispatch.

    Within each phase, all nodes run concurrently up to max_parallel.
    Phases execute sequentially (phase N+1 starts after all phase N nodes complete).
    """

    def __init__(self, max_parallel: int = 5, emit_events: bool = True):
        self.max_parallel = max_parallel
        self.emit_events = emit_events
        self._events: list[AgentEvent] = []
        self._workflow_id: str = ""

    @property
    def events(self) -> list[AgentEvent]:
        return list(self._events)

    def _emit(self, event: AgentEvent) -> None:
        if self.emit_events:
            self._events.append(event)

    async def execute(
        self,
        graph: AgentExecutionGraph,
        workflow_id: str = "parallel_graph",
        global_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute all nodes in the graph phase by phase.

        Returns merged artifacts and execution results.
        """
        self._workflow_id = workflow_id
        ctx = dict(global_context or {})

        logger.info(
            "ParallelExecutor: starting graph=%d nodes max_parallel=%d",
            len(graph.nodes), self.max_parallel,
        )

        _counter: list[int] = [0]

        while not graph.is_complete:
            ready = graph.get_ready_nodes()
            if not ready:
                if graph.is_blocked:
                    logger.warning("ParallelExecutor: graph is blocked — failing nodes remain")
                    break
                await asyncio.sleep(0.05)
                continue

            # Limit to max_parallel
            batch = ready[:self.max_parallel]
            logger.info(
                "ParallelExecutor: phase=%d batch=%d/%d nodes",
                batch[0].phase if batch else -1,
                len(batch), len(ready),
            )

            async def _run_node(node: GraphNode) -> None:
                """Execute a single graph node via its assigned agent."""
                _counter[0] += 1
                graph.mark_running(node.node_id)
                self._emit(AgentEvent.node_started(
                    workflow_id, node.node_id, node.agent_id, node.goal, node.phase,
                ))

                agent = get_agent(node.agent_id)
                if not agent:
                    err = f"No agent registered for: {node.agent_id}"
                    graph.mark_failed(node.node_id, err)
                    self._emit(AgentEvent.node_failed(
                        workflow_id, node.node_id, node.agent_id, err,
                    ))
                    return

                ec = ExecutionContext(
                    workflow_id=f"{workflow_id}_n{node.node_id}",
                    owner="planner",
                    session_id="",
                    variables=dict(node.parameters),
                )
                if ctx:
                    for k, v in ctx.items():
                        if k not in ec.variables:
                            ec.variables[k] = v

                # Inject upstream artifact IDs from dependency nodes
                if node.depends_on:
                    for dep_id in node.depends_on:
                        dep_node = graph.nodes.get(dep_id)
                        if dep_node and dep_node.status == NodeStatus.COMPLETED:
                            for art_key, art_val in dep_node.artifacts.items():
                                if art_key not in ec.variables:
                                    ec.variables[art_key] = art_val
                            if dep_node.result:
                                for art_key, art_val in dep_node.result.get("_artifacts", {}).items():
                                    if art_key not in ec.variables:
                                        ec.variables[art_key] = art_val

                # Inject specific input_artifact mappings
                # input_artifacts maps upstream_artifact_key -> downstream_param_key
                if node.input_artifacts:
                    for artifact_key, param_key in node.input_artifacts.items():
                        for dep_id in node.depends_on:
                            dep_node = graph.nodes.get(dep_id)
                            if dep_node and dep_node.status == NodeStatus.COMPLETED:
                                if artifact_key in dep_node.artifacts:
                                    ec.variables[param_key] = dep_node.artifacts[artifact_key]
                                elif dep_node.result and artifact_key in dep_node.result.get("_artifacts", {}):
                                    ec.variables[param_key] = dep_node.result["_artifacts"][artifact_key]

                try:
                    result = await agent.execute(ec)
                except Exception as e:
                    err = f"Exception in {node.agent_id}: {e}"
                    logger.exception("ParallelExecutor: %s", err)
                    graph.mark_failed(node.node_id, err)
                    self._emit(AgentEvent.node_failed(
                        workflow_id, node.node_id, node.agent_id, err,
                    ))
                    return

                step_ok = (
                    result.get("exit_code", -1) == 0
                    or result.get("sent") is True
                    or result.get("success", False) is True
                )

                if step_ok:
                    task_artifacts = result.get("_artifacts", {})
                    graph.mark_completed(node.node_id, result, task_artifacts)
                    self._emit(AgentEvent.node_completed(
                        workflow_id, node.node_id, node.agent_id, result,
                    ))
                    logger.info(
                        "ParallelExecutor: %s OK artifacts=%s",
                        node.node_id, list(task_artifacts.keys()),
                    )
                else:
                    err = result.get("error") or f"{node.agent_id} failed"
                    graph.mark_failed(node.node_id, err)
                    self._emit(AgentEvent.node_failed(
                        workflow_id, node.node_id, node.agent_id, err,
                    ))
                    logger.warning("ParallelExecutor: %s FAIL: %s", node.node_id, err)

            # Run batch concurrently
            async with asyncio.TaskGroup() as tg:
                for node in batch:
                    tg.create_task(_run_node(node))

        # Collect results
        all_artifacts = graph.get_all_artifacts()
        errors = graph.get_all_errors()
        total = len(graph.nodes)
        failed = sum(1 for n in graph.nodes.values() if n.status == NodeStatus.FAILED)

        self._emit(AgentEvent.graph_completed(
            workflow_id, total_nodes=total, failed_nodes=failed,
        ))

        logger.info(
            "ParallelExecutor: done %d/%d nodes, %d failed, %d artifacts",
            total - failed, total, failed, len(all_artifacts),
        )

        return {
            "artifacts": all_artifacts,
            "error": "; ".join(errors) if errors else None,
            "graph": graph,
            "total_nodes": total,
            "failed_nodes": failed,
        }
