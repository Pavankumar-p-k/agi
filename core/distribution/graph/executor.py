from __future__ import annotations

import asyncio

from ..contracts import WorkerRequest
from .models import GraphState, NodeStatus
from .scheduler import DependencyAwareScheduler


class GraphExecutor:
    def __init__(self, scheduler=None, registry=None):
        self.registry = registry or (scheduler.registry if scheduler else None)
        self.scheduler = scheduler or DependencyAwareScheduler(self.registry)
        self._cancelled = False
        self._tasks = set()

    async def execute(self, graph):
        self._cancelled = False
        graph.state = GraphState.RUNNING
        try:
            while graph.has_unfinished():
                if self._cancelled:
                    for node in graph.nodes.values():
                        if node.status in (NodeStatus.PENDING, NodeStatus.RUNNING):
                            node.status = NodeStatus.CANCELLED
                    graph.state = GraphState.CANCELLED
                    return graph
                assignments = await self.scheduler.schedule_ready_nodes(graph)
                if not assignments:
                    if any(n.status == NodeStatus.RUNNING for n in graph.nodes.values()):
                        await asyncio.sleep(0)
                        continue
                    graph.state = GraphState.FAILED
                    return graph
                tasks = [asyncio.create_task(self._run_node(graph, node, worker_id))
                         for node, worker_id in assignments]
                self._tasks.update(tasks)
                await asyncio.gather(*tasks, return_exceptions=True)
                self._tasks.difference_update(tasks)
                if any(n.status == NodeStatus.FAILED for n in graph.nodes.values()):
                    graph.state = GraphState.FAILED
                    return graph
            graph.state = GraphState.COMPLETED
            return graph
        except asyncio.CancelledError:
            graph.state = GraphState.CANCELLED
            raise

    async def _run_node(self, graph, node, worker_id):
        worker = self.registry.get(worker_id)
        try:
            response = await worker.worker.execute(WorkerRequest(request=node.request))
            node.result = response
            node.status = NodeStatus.COMPLETED
        except Exception as exc:
            node.status, node.error = NodeStatus.FAILED, str(exc)
            await self.scheduler.on_node_failed(graph, node.id, exc)

    async def cancel(self):
        self._cancelled = True
        for task in list(self._tasks):
            task.cancel()
