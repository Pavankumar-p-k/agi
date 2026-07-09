"""Graph recovery — resume a failed or paused graph from its last checkpoint.

The recovery process:
1. Load the checkpoint snapshot.
2. Rebuild the ``DistributedGraph`` with original node requests.
3. Reset failed/pending nodes to ``PENDING`` so they can be re-scheduled.
4. Return the recovered graph for re-execution.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from core.distribution.graph.checkpoint import GraphCheckpointer
from core.distribution.graph.models import (
    DistributedGraph,
    GraphEdge,
    GraphNode,
    GraphState,
    NodeStatus,
)

logger = logging.getLogger(__name__)


class GraphRecovery:
    """Recovers a ``DistributedGraph`` from a checkpoint for re-execution."""

    def __init__(self, checkpointer: GraphCheckpointer | None = None) -> None:
        self._checkpointer = checkpointer or GraphCheckpointer()

    async def recover(
        self,
        graph_id: str,
        original_nodes: dict[str, GraphNode],
    ) -> DistributedGraph | None:
        """Rebuild a recoverable ``DistributedGraph`` from its checkpoint.

        Args:
            graph_id: The ID of the graph to recover.
            original_nodes: The original ``GraphNode``\ s (with their ``Request``\ s).

        Returns:
            A recovered graph ready for re-execution, or ``None`` if no
            checkpoint exists.
        """
        snapshot = await self._checkpointer.load(graph_id)
        if snapshot is None:
            return None

        graph = DistributedGraph.from_snapshot(snapshot, original_nodes)
        if graph.is_terminal():
            logger.warning("[Recovery] Graph %s already in terminal state %s — nothing to recover", graph_id, graph.state.name)
            return None

        for node in graph.nodes.values():
            if node.status in (NodeStatus.RUNNING, NodeStatus.FAILED):
                logger.info("[Recovery] Resetting node %s from %s → PENDING", node.id, node.status.name)
                node.status = NodeStatus.PENDING
                node.worker_id = None
                node.error = None
                node.retry_count = 0

        graph.state = GraphState.PENDING
        graph.updated_at = datetime.now()
        logger.info("[Recovery] Graph %s recovered with %d node(s)", graph_id, len(graph.nodes))
        return graph

    async def has_checkpoint(self, graph_id: str) -> bool:
        snap = await self._checkpointer.load(graph_id)
        return snap is not None
