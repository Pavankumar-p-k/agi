"""GraphRecovery — rebuild a runnable graph from a checkpoint.

Recovery needs the original node objects because a snapshot only carries
serialisable state; ``recover()`` therefore takes ``original_nodes``
(Rule 46). Completed graphs are not recovered.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.distribution.graph.checkpoint import GraphCheckpointer
from core.distribution.graph.models import (
    DistributedGraph,
    GraphState,
    NodeStatus,
)

logger = logging.getLogger(__name__)


class GraphRecovery:
    """Restores interrupted graphs to a re-runnable state."""

    def __init__(self, checkpointer: Optional[GraphCheckpointer] = None) -> None:
        self.checkpointer = checkpointer or GraphCheckpointer()

    async def recover(self, graph_id: str, original_nodes: Optional[dict] = None) -> Optional[DistributedGraph]:
        """Rebuild *graph_id* from its checkpoint, or None when not recoverable."""
        snapshot = await self.checkpointer.load(graph_id)
        if not snapshot:
            return None
        state = str(snapshot.get("state", GraphState.PENDING.value))
        if state in (GraphState.COMPLETED.value, GraphState.CANCELLED.value):
            logger.info("graph %s is %s — nothing to recover", graph_id, state)
            return None

        graph = DistributedGraph.from_snapshot(snapshot, original_nodes or {})
        # Everything non-terminal is re-armed for execution.
        for node in graph.nodes.values():
            if node.status in (NodeStatus.RUNNING, NodeStatus.FAILED):
                node.status = NodeStatus.PENDING
                node.error = None
        graph.state = GraphState.PENDING
        return graph


__all__ = ["GraphRecovery"]
