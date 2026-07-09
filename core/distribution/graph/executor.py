"""Executes a ``DistributedGraph`` across workers.

Orchestrates the schedule → dispatch → collect → checkpoint lifecycle
for each node in the graph, with cancellation and error propagation.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from core.distribution.contracts import WorkerRequest, WorkerResponse
from core.distribution.graph.checkpoint import GraphCheckpointer
from core.distribution.graph.models import (
    DistributedGraph,
    GraphNode,
    GraphState,
    NodeStatus,
)
from core.distribution.graph.scheduler import DependencyAwareScheduler
from core.distribution.registry import WorkerRegistry, get_worker_registry
from core.distribution.transport import Transport
from core.runtime import RuntimeContext

logger = logging.getLogger(__name__)


class GraphExecutor:
    """Drives a ``DistributedGraph`` to completion across available workers."""

    def __init__(
        self,
        scheduler: DependencyAwareScheduler | None = None,
        transport: Transport | None = None,
        registry: WorkerRegistry | None = None,
        checkpointer: GraphCheckpointer | None = None,
        poll_interval: float = 0.5,
    ) -> None:
        self._registry = registry or get_worker_registry()
        self._scheduler = scheduler or DependencyAwareScheduler(self._registry)
        from core.distribution.transport import InProcessTransport
        self._transport = transport or InProcessTransport(registry=self._registry)
        self._checkpointer = checkpointer or GraphCheckpointer()
        self._poll_interval = poll_interval
        self._cancel_event = asyncio.Event()

    async def execute(
        self,
        graph: DistributedGraph,
        runtime_context: RuntimeContext | None = None,
    ) -> DistributedGraph:
        """Execute *graph* to completion. Returns the final graph state."""
        logger.info("[GraphExecutor] Starting graph %s (%d nodes)", graph.id, len(graph.nodes))
        graph.state = GraphState.RUNNING

        while graph.has_unfinished() and not graph.is_terminal():
            if self._cancel_event.is_set():
                logger.warning("[GraphExecutor] Graph %s cancelled", graph.id)
                graph.state = GraphState.CANCELLED
                for node in graph.nodes.values():
                    if node.status in (NodeStatus.PENDING, NodeStatus.RUNNING):
                        node.status = NodeStatus.CANCELLED
                break

            assignments = await self._scheduler.schedule_ready_nodes(graph)
            if not assignments:
                if graph.has_unfinished():
                    await asyncio.sleep(self._poll_interval)
                continue

            dispatch_tasks = [
                asyncio.create_task(self._dispatch(node, worker_id, runtime_context))
                for node, worker_id in assignments
            ]
            pending: set[asyncio.Task] = set(dispatch_tasks)

            while pending and not self._cancel_event.is_set():
                done, pending = await asyncio.wait(pending, timeout=self._poll_interval)

            if self._cancel_event.is_set():
                for t in pending:
                    t.cancel()
                graph.state = GraphState.CANCELLED
                for node in graph.nodes.values():
                    if node.status in (NodeStatus.PENDING, NodeStatus.RUNNING):
                        node.status = NodeStatus.CANCELLED
                break

            results: list[Any] = []
            for t in dispatch_tasks:
                try:
                    results.append(t.result())
                except Exception as e:
                    results.append(e)

            for node, result in zip([a[0] for a in assignments], results):
                if isinstance(result, Exception):
                    await self._scheduler.on_node_failed(graph, node.id, str(result))
                elif result is not None:
                    node.result = result
                    node.status = NodeStatus.COMPLETED
                    node.completed_at = datetime.now()
                    logger.debug("[GraphExecutor] Node %s completed on %s", node.id, node.worker_id)

            await self._checkpointer.save(graph)

        if graph.state not in (GraphState.CANCELLED, GraphState.FAILED):
            any_failed = any(n.status == NodeStatus.FAILED for n in graph.nodes.values())
            graph.state = GraphState.FAILED if any_failed else GraphState.COMPLETED

        logger.info("[GraphExecutor] Graph %s final state: %s", graph.id, graph.state.name)
        return graph

    async def cancel(self) -> None:
        """Request cancellation of the currently executing graph."""
        self._cancel_event.set()

    async def _dispatch(
        self,
        node: GraphNode,
        worker_id: str,
        runtime_context: RuntimeContext | None,
    ) -> dict[str, Any] | None:
        node.started_at = datetime.now()
        try:
            registration = self._registry.get_worker(worker_id)
            if registration is None:
                raise RuntimeError(f"Worker {worker_id} not found in registry")
            worker_endpoint = registration.worker

            wr = WorkerRequest(
                runtime_context=runtime_context or RuntimeContext.__new__(RuntimeContext),
                request=node.request,
                pipeline_version="1.0",
                runtime_spec_version="1.0",
                worker_protocol_version="1.0",
            )
            response: WorkerResponse = await self._transport.send(wr, address=worker_id)
            return {
                "text": response.outcome.text if response.outcome else "",
                "observations": list(response.observations) if response.observations else [],
                "metrics": response.metrics.to_dict() if response.metrics else {},
            }
        except Exception as exc:
            node.error = str(exc)
            node.retry_count += 1
            if node.retry_count <= node.max_retries:
                logger.warning(
                    "[GraphExecutor] Node %s failed (retry %d/%d): %s",
                    node.id, node.retry_count, node.max_retries, exc,
                )
                node.status = NodeStatus.PENDING
                return None
            raise
