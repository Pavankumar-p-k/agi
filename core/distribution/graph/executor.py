"""GraphExecutor — runs a DistributedGraph to completion.

Nodes are dispatched through the :class:`Transport` protocol (Rule 43); the
executor never reaches into pipeline internals or worker state directly.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from core.distribution.contracts import (
    ExecutionAffinity,
    WorkerRequest,
    WorkerResponse,
)
from core.distribution.graph.models import (
    DistributedGraph,
    GraphNode,
    GraphState,
    NodeStatus,
)
from core.distribution.graph.scheduler import DependencyAwareScheduler
from core.distribution.registry import get_worker_registry
from core.distribution.transport import InProcessTransport, Transport

logger = logging.getLogger(__name__)


class GraphExecutor:
    """Executes graph nodes in dependency order."""

    def __init__(self, scheduler: Optional[DependencyAwareScheduler] = None,
                 registry: Any = None,
                 transport: Optional[Transport] = None) -> None:
        self.registry = registry if registry is not None else get_worker_registry()
        self.scheduler = scheduler or DependencyAwareScheduler(self.registry)
        self.transport = transport
        self._cancelled = False
        self._inflight: dict = {}

    # ── execution ───────────────────────────────────────────────────
    async def execute(self, graph: DistributedGraph) -> DistributedGraph:
        """Run every node; returns the graph with its final state."""
        self._cancelled = False
        self._inflight = {}
        graph.state = GraphState.RUNNING
        try:
            while not self._cancelled and graph.has_unfinished():
                assignments = await self.scheduler.schedule_ready_nodes(graph)
                if not assignments:
                    if self._cancelled:
                        break
                    ready = graph.get_ready_nodes()
                    if ready:
                        for node in ready:
                            node.status = NodeStatus.FAILED
                            node.error = node.error or "no compatible worker available"
                        graph.state = GraphState.FAILED
                    break
                tasks = [
                    asyncio.ensure_future(self._run_node(graph, node, worker_id))
                    for node, worker_id in assignments
                ]
                self._inflight = {task: node for task, (node, _w) in
                                  zip(tasks, assignments)}
                await asyncio.gather(*tasks, return_exceptions=True)
                self._inflight = {}
        finally:
            self._inflight = {}

        if self._cancelled:
            for node in graph.nodes.values():
                if not node.is_terminal:
                    node.status = NodeStatus.CANCELLED
            graph.state = GraphState.CANCELLED
        elif graph.state == GraphState.RUNNING:
            if graph.has_unfinished():
                graph.state = GraphState.FAILED
            else:
                graph.state = GraphState.COMPLETED
        return graph

    async def _run_node(self, graph: DistributedGraph, node: GraphNode,
                        worker_id: str) -> None:
        registration = None
        registry = self.registry
        if hasattr(registry, "get"):
            registration = registry.get(worker_id)
        attempt = 0
        while True:
            attempt += 1
            node.attempts = attempt
            try:
                response = await self._dispatch(node, worker_id, registration)
            except asyncio.CancelledError:
                node.status = NodeStatus.CANCELLED
                raise
            except Exception as exc:  # noqa: BLE001 — converted to node failure
                if attempt <= max(0, int(node.max_retries or 0)):
                    continue
                node.status = NodeStatus.FAILED
                node.error = f"{type(exc).__name__}: {exc}"
                await self.scheduler.on_node_failed(graph, node.id, node.error)
                return

            if response is not None and getattr(response, "success", True) is False:
                if attempt <= max(0, int(node.max_retries or 0)):
                    continue
                node.status = NodeStatus.FAILED
                node.error = getattr(response, "error", None) or "worker reported failure"
                await self.scheduler.on_node_failed(graph, node.id, node.error)
                return

            node.status = NodeStatus.COMPLETED
            node.result = getattr(response, "outcome", response)
            node.error = None
            return

    async def _dispatch(self, node: GraphNode, worker_id: str,
                        registration: Any) -> Optional[WorkerResponse]:
        request = WorkerRequest(
            request=node.request,
            worker_id=worker_id,
            capability=node.metadata.get("capability"),
        )
        transport = self.transport
        if transport is None:
            worker_fn = getattr(getattr(registration, "worker", None), "execute", None)
            if worker_fn is None:
                raise RuntimeError(f"worker {worker_id} exposes no execute()")
            transport = InProcessTransport(worker_fn=worker_fn)
        return await transport.send(request)

    # ── control ─────────────────────────────────────────────────────
    async def cancel(self, graph: Optional[DistributedGraph] = None) -> None:
        """Cancel every in-flight node and stop scheduling new ones."""
        self._cancelled = True
        inflight = list(self._inflight)
        for task in inflight:
            task.cancel()
        if inflight:
            await asyncio.gather(*inflight, return_exceptions=True)
        if graph is not None:
            for node in graph.nodes.values():
                if not node.is_terminal:
                    node.status = NodeStatus.CANCELLED
            graph.state = GraphState.CANCELLED


__all__ = ["GraphExecutor"]
