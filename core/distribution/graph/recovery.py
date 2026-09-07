from __future__ import annotations

from .models import GraphState, NodeStatus
from .checkpoint import GraphCheckpointer


class GraphRecovery:
    def __init__(self, checkpointer=None):
        self.checkpointer = checkpointer or GraphCheckpointer()

    async def recover(self, graph_id, original_nodes):
        snapshot = await self.checkpointer.load(graph_id)
        if snapshot is None or snapshot.get("state") in (GraphState.COMPLETED.value, GraphState.CANCELLED.value):
            return None
        graph = __import__("core.distribution.graph.models", fromlist=["DistributedGraph"]).DistributedGraph.from_snapshot(snapshot, original_nodes)
        graph.state = GraphState.PENDING
        for node in graph.nodes.values():
            if node.status in (NodeStatus.RUNNING, NodeStatus.FAILED, NodeStatus.CANCELLED):
                node.status = NodeStatus.PENDING
        return graph
