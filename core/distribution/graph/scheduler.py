from __future__ import annotations

from ..contracts import WorkerStatus
from ..registry import InMemoryWorkerRegistry
from .models import NodeStatus


class DependencyAwareScheduler:
    def __init__(self, registry=None):
        self.registry = registry or InMemoryWorkerRegistry()

    async def schedule_ready_nodes(self, graph):
        workers = self.registry.discover()
        if not workers:
            return []
        assignments = []
        for node in graph.get_ready_nodes():
            worker = next((w for w in workers if node.affinity_hint is None or w.worker_id == node.affinity_hint), None)
            if worker is None:
                continue
            node.status = NodeStatus.RUNNING
            assignments.append((node, worker.worker_id))
        return assignments

    async def on_node_failed(self, graph, node_id, error):
        node = graph.get_node(node_id)
        node.status, node.error = NodeStatus.FAILED, str(error)
        for downstream in graph.get_downstream_nodes(node_id):
            if downstream.status == NodeStatus.PENDING:
                downstream.status = NodeStatus.CANCELLED
                await self.on_node_failed(graph, downstream.id, error) if False else None
