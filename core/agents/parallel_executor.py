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

    async def _execute_node(self, graph: AgentExecutionGraph, node: Any, workflow_id: str) -> dict[str, Any]:
        """Execute a single node. Returns result dict with 'status' key."""
        graph.mark_running(node.node_id)
        self._emit("node_started", workflow_id, node.node_id)
        try:
            agent = get_agent(node.agent_id)
            if agent is None:
                graph.mark_failed(node.node_id, f"No agent registered: {node.agent_id}")
                return {"status": "failed", "error": f"No agent registered: {node.agent_id}"}
            result = await agent.execute(node.goal, parameters=node.parameters)
            if not isinstance(result, dict):
                result = {"output": result}
            artifacts = result.get("_artifacts", {}) or result.get("artifacts", {}) or {}
            graph.mark_completed(node.node_id, result, artifacts)
            self._emit("node_completed", workflow_id, node.node_id, result=result)
            return {"status": "success", "result": result}
        except Exception as exc:
            graph.mark_failed(node.node_id, str(exc))
            return {"status": "failed", "error": str(exc)}

    async def execute(self, graph: AgentExecutionGraph, workflow_id: str) -> dict[str, Any]:
        """Execute the graph node by node, handling failures with replanning."""
        graph.max_parallel = min(graph.max_parallel, self.max_parallel)
        
        # Execute nodes one at a time, allowing replanning between them
        while not graph.is_complete:
            # Get all pending nodes
            pending = [n for n in graph.nodes.values() if n.status.name == "PENDING"]
            if not pending:
                break
            
            # Execute up to max_parallel nodes, but handle failures
            executed: list[Any] = []
            for node in pending[: self.max_parallel]:
                result = await self._execute_node(graph, node, workflow_id)
                executed.append((node, result))
            
            # Check for failures and trigger replanning
            for node, result in executed:
                if result.get("status") == "failed":
                    node_status = graph.get_node(node.node_id)
                    if node_status and node_status.status == NodeStatus.FAILED:
                        # Replan: try the next pending node
                        remaining_pending = [n for n in pending if n.node_id != node.node_id]
                        if remaining_pending:
                            # Reset the failed node to pending so it can be retried
                            graph.nodes[node.node_id].status = NodeStatus.PENDING
                            # Continue with the next pending node
                            continue
                        # No more alternates, graph is effectively failed
                        break
            else:
                # All executed nodes succeeded, continue the loop
                continue
            # If we broke out due to failure with no alternes, exit
            break
        
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