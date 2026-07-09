"""Dependency-aware scheduler for distributed DAG execution.

Resolves graph dependencies and assigns ready nodes to workers
sourced from the ``WorkerRegistry``.
"""
from __future__ import annotations

import logging
from typing import Any

from core.distribution.contracts import ExecutionAffinity
from core.distribution.graph.models import DistributedGraph, GraphNode, GraphState, NodeStatus
from core.distribution.registry import WorkerRegistry, get_worker_registry

logger = logging.getLogger(__name__)


class DependencyAwareScheduler:
    """Schedules graph nodes to workers respecting dependency order and affinities."""

    def __init__(
        self,
        registry: WorkerRegistry | None = None,
    ) -> None:
        self._registry = registry or get_worker_registry()

    async def schedule_ready_nodes(
        self,
        graph: DistributedGraph,
        limit: int = 0,
    ) -> list[tuple[GraphNode, str]]:
        """Return ``(node, worker_id)`` pairs for all currently-ready nodes.

        Args:
            graph: The distributed graph to schedule.
            limit: Max nodes to schedule (``0`` = no limit).

        Returns:
            Pairs of (node, worker_id) for nodes that are ready and can be assigned.
        """
        ready = graph.get_ready_nodes()
        if limit > 0:
            ready = ready[:limit]

        workers = self._registry.discover()
        if not workers:
            logger.warning("[GraphScheduler] No workers available — cannot schedule ready nodes")
            return []

        assignments: list[tuple[GraphNode, str]] = []
        worker_ids = [w.worker_id for w in workers if w.worker_id]

        for node in ready:
            worker_id = await self._select_worker(node, worker_ids)
            node.worker_id = worker_id
            node.status = NodeStatus.RUNNING
            assignments.append((node, worker_id))

        if assignments:
            logger.info(
                "[GraphScheduler] Scheduled %d node(s) across %d worker(s)",
                len(assignments), len(worker_ids),
            )
        return assignments

    async def _select_worker(
        self,
        node: GraphNode,
        worker_ids: list[str],
    ) -> str:
        if not worker_ids:
            raise RuntimeError("No workers available to schedule node")
        if node.affinity_hint and node.affinity_hint in worker_ids:
            return node.affinity_hint
        idx = hash(node.id) % len(worker_ids)
        return worker_ids[idx]

    async def on_node_failed(
        self,
        graph: DistributedGraph,
        node_id: str,
        error: str,
    ) -> None:
        """Mark *node_id* as failed and cascade cancellation to downstream nodes."""
        node = graph.get_node(node_id)
        if node is None:
            return
        node.status = NodeStatus.FAILED
        node.error = error

        for downstream in graph.get_downstream_nodes(node_id):
            if downstream.status == NodeStatus.PENDING:
                downstream.status = NodeStatus.CANCELLED
                downstream.error = f"Cancelled due to upstream failure: {node_id}"

        failed = any(n.status == NodeStatus.FAILED for n in graph.nodes.values())
        if failed:
            graph.state = GraphState.FAILED
            logger.warning("[GraphScheduler] Graph %s marked FAILED due to node %s", graph.id, node_id)
