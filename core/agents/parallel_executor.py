"""Async execution of phase-aware agent graphs."""
from __future__ import annotations

import asyncio
from typing import Any

from core.agents.events import AgentEvent
from core.agents.graph import AgentExecutionGraph, NodeStatus
from core.agents.router import get_agent


class ParallelAgentExecutor:
    def __init__(self, max_parallel: int = 3, emit_events: bool = True):
        self.max_parallel = max_parallel
        self.emit_events = emit_events
        self.events: list[AgentEvent] = []

    def _emit(self, event_type: str, workflow_id: str, node_id: str | None = None, **data: Any) -> None:
        if self.emit_events:
            self.events.append(AgentEvent(event_type, workflow_id, node_id, data))

    async def _execute_node(self, graph: AgentExecutionGraph, node, workflow_id: str) -> None:
        graph.mark_running(node.node_id)
        self._emit("node_started", workflow_id, node.node_id)
        try:
            agent = get_agent(node.agent_id)
            if agent is None:
                graph.mark_failed(node.node_id, f"No agent registered: {node.agent_id}")
                self._emit("node_failed", workflow_id, node.node_id, error=graph.get_node(node.node_id).error)
                return
            result = await agent.execute(node.goal, parameters=node.parameters)
            if not isinstance(result, dict):
                result = {"output": result}
            artifacts = result.get("_artifacts", {}) or result.get("artifacts", {}) or {}
            graph.mark_completed(node.node_id, result, artifacts)
            self._emit("node_completed", workflow_id, node.node_id, result=result)
        except Exception as exc:
            graph.mark_failed(node.node_id, str(exc))
            self._emit("node_failed", workflow_id, node.node_id, error=str(exc))

    async def execute(self, graph: AgentExecutionGraph, workflow_id: str) -> dict[str, Any]:
        graph.max_parallel = min(graph.max_parallel, self.max_parallel)
        while not graph.is_complete:
            ready = graph.get_ready_nodes()
            if not ready:
                break
            await asyncio.gather(*(self._execute_node(graph, node, workflow_id) for node in ready))
        result = {
            "workflow_id": workflow_id,
            "success": graph.is_complete and not any(n.status == NodeStatus.FAILED for n in graph.nodes.values()),
            "artifacts": graph.get_all_artifacts(),
        }
        self._emit(
            "graph_completed",
            workflow_id=workflow_id,
            success=result["success"],
            artifacts=result["artifacts"],
        )
        return result
