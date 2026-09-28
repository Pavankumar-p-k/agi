"""DependencyAwareScheduler — assigns ready nodes to workers.

Node failures cascade: every downstream node is marked CANCELLED so a failed
precondition can never be silently skipped (Rule 47).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.distribution.graph.models import (
    DistributedGraph,
    GraphNode,
    GraphState,
    NodeStatus,
)
from core.distribution.registry import get_worker_registry

logger = logging.getLogger(__name__)


class DependencyAwareScheduler:
    """Places ready nodes on compatible workers."""

    def __init__(self, registry: Any = None) -> None:
        self.registry = registry
        self._cursor = 0

    def _registry(self) -> Any:
        return self.registry if self.registry is not None else get_worker_registry()

    def _select(self, node: GraphNode, candidates: list) -> Optional[Any]:
        if not candidates:
            return None
        if node.affinity_hint:
            for reg in candidates:
                if reg.worker_id == node.affinity_hint:
                    return reg
            return None
        chosen = candidates[self._cursor % len(candidates)]
        self._cursor = (self._cursor + 1) % max(1, len(candidates))
        return chosen

    async def schedule_ready_nodes(self, graph: DistributedGraph) -> list:
        """Assign every ready node to a worker. Returns [(node, worker_id)]."""
        assignments: list = []
        ready = graph.get_ready_nodes()
        if not ready:
            return assignments
        registry = self._registry()
        for node in ready:
            candidates = registry.discover(capability=node.metadata.get("capability"))
            eligible = [
                reg for reg in candidates
                if registry.check_version_compatibility(reg).compatible
            ]
            chosen = self._select(node, eligible)
            if chosen is None:
                continue
            node.worker_id = chosen.worker_id
            node.status = NodeStatus.RUNNING
            assignments.append((node, chosen.worker_id))
        if assignments and graph.state == GraphState.PENDING:
            graph.state = GraphState.RUNNING
        return assignments

    async def on_node_failed(self, graph: DistributedGraph, node_id: str,
                             reason: str = "") -> list:
        """Mark *node_id* FAILED and cancel every downstream node."""
        node = graph.get_node(node_id)
        if node is not None:
            node.status = NodeStatus.FAILED
            node.error = reason or node.error
        cancelled: list = []
        for downstream in graph.get_downstream_nodes(node_id):
            if downstream.status in (NodeStatus.COMPLETED, NodeStatus.FAILED):
                continue
            downstream.status = NodeStatus.CANCELLED
            downstream.error = downstream.error or f"upstream {node_id} failed"
            cancelled.append(downstream)
        if cancelled:
            logger.info("cancelled %d downstream node(s) after %s failed",
                        len(cancelled), node_id)
        return cancelled

    async def on_node_completed(self, graph: DistributedGraph, node_id: str,
                                result: Any = None) -> None:
        node = graph.get_node(node_id)
        if node is not None:
            node.status = NodeStatus.COMPLETED
            node.result = result


__all__ = ["DependencyAwareScheduler"]
