"""ParallelAgentExecutor — executes an AgentExecutionGraph concurrently.

Nodes within a phase run in parallel (bounded by max_parallel); the next
phase opens only when every node of the current phase is terminal.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from core.agents.events import AgentEvent
from core.agents.graph import AgentExecutionGraph, NodeStatus

# Module-level import so tests can patch core.agents.parallel_executor.get_agent
from core.agents.router import get_agent


class ParallelAgentExecutor:
    def __init__(self, max_parallel: int = 5, emit_events: bool = True, **kwargs: Any):
        self.max_parallel = max(1, int(max_parallel))
        self.emit_events = emit_events
        self.events: list[AgentEvent] = []

    def _emit(self, event_type: str, node=None, workflow_id: str = "", **data: Any) -> None:
        if not self.emit_events:
            return
        self.events.append(AgentEvent(
            event_type=event_type,
            node_id=getattr(node, "node_id", ""),
            agent_id=getattr(node, "agent_id", ""),
            workflow_id=workflow_id,
            data=data,
        ))

    async def execute(self, graph: AgentExecutionGraph, workflow_id: str = "",
                      **kwargs: Any) -> dict[str, Any]:
        self._emit("graph_started", workflow_id=workflow_id)
        try:
            await self._run(graph, workflow_id)
        finally:
            self._emit("graph_completed", workflow_id=workflow_id,
                       complete=graph.is_complete)
        return {
            "workflow_id": workflow_id,
            "artifacts": graph.get_all_artifacts(),
            "complete": graph.is_complete,
            "blocked": graph.is_blocked,
        }

    async def _run(self, graph: AgentExecutionGraph, workflow_id: str) -> None:
        while not graph.is_complete:
            ready = graph.get_ready_nodes()
            if not ready:
                break  # blocked or nothing schedulable
            for batch_start in range(0, len(ready), self.max_parallel):
                batch = ready[batch_start:batch_start + self.max_parallel]
                await asyncio.gather(*[
                    self._run_node(graph, node, workflow_id, get_agent)
                    for node in batch
                ])

    async def _run_node(self, graph: AgentExecutionGraph, node, workflow_id: str,
                        get_agent) -> None:
        agent = get_agent(node.agent_id)
        if agent is None:
            graph.mark_failed(node.node_id, f"No agent registered for '{node.agent_id}'")
            self._emit("node_failed", node, workflow_id, error="no agent")
            return
        graph.mark_running(node.node_id)
        self._emit("node_started", node, workflow_id)
        try:
            result = await agent.execute(node.goal, **(node.parameters or {}))
            if isinstance(result, dict):
                # Tool-style dict result: {'output', 'exit_code'[, 'error', '_artifacts']}
                success = result.get("success", result.get("exit_code", 0) == 0)
                output = result
                artifacts = result.get("_artifacts") or {}
                error = str(result.get("error", "") or "")
            else:
                success = bool(getattr(result, "success", False))
                output = result.to_dict() if hasattr(result, "to_dict") else {
                    "output": str(result)}
                artifacts = getattr(result, "artifacts", None) or {}
                error = str(getattr(result, "error", "") or "")
            if success:
                graph.mark_completed(node.node_id, output=output, artifacts=artifacts)
                self._emit("node_completed", node, workflow_id)
            else:
                graph.mark_failed(node.node_id, error or "agent failed")
                self._emit("node_failed", node, workflow_id)
        except Exception as exc:  # noqa: BLE001 — isolate node failures
            graph.mark_failed(node.node_id, f"{type(exc).__name__}: {exc}")
            self._emit("node_failed", node, workflow_id, error=str(exc))
