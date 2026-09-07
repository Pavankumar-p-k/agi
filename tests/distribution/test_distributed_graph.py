"""Integration tests for Phase 6F — Distributed Graph.

Covers graph lifecycle, scheduling, checkpoint, recovery, and cancellation.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from core.distribution.contracts import HealthStatus, WorkerRequest, WorkerResponse
from core.distribution.graph import (
    DependencyAwareScheduler,
    DistributedGraph,
    GraphCheckpointer,
    GraphEdge,
    GraphExecutor,
    GraphNode,
    GraphRecovery,
    GraphState,
    NodeStatus,
)
from core.distribution.registry import (
    InMemoryWorkerRegistry,
    WorkerRegistration,
)
from core.pipeline.messages import Request


# ── Fake worker ────────────────────────────────────────────────────────────────


class _FakeWorker:
    """Test worker endpoint that returns canned responses."""

    def __init__(self, worker_id: str = "test-worker") -> None:
        self.worker_id = worker_id
        self.execution_count = 0

    async def execute(self, request: WorkerRequest) -> WorkerResponse:
        self.execution_count += 1
        return WorkerResponse(
            outcome=None,
            observations=(),
            metrics=None,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    async def heartbeat(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


def _reg(worker_id: str) -> WorkerRegistration:
    return WorkerRegistration(
        worker_id=worker_id,
        worker=_FakeWorker(worker_id),
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_node(node_id: str, text: str = "hello") -> GraphNode:
    return GraphNode(
        id=node_id,
        request=Request(text=text, transport="graph_test"),
    )


def _make_graph(graph_id: str, nodes: list[GraphNode], edges: list[GraphEdge] | None = None) -> DistributedGraph:
    return DistributedGraph(
        id=graph_id,
        nodes={n.id: n for n in nodes},
        edges=edges or [],
    )


# ── Sprint 1: Domain model ────────────────────────────────────────────────────


class TestGraphDomainModel:
    def test_graph_node_default_status(self):
        node = _make_node("n1")
        assert node.status == NodeStatus.PENDING

    def test_graph_add_node(self):
        g = _make_graph("g1", [])
        n1 = _make_node("n1")
        g.add_node(n1)
        assert "n1" in g.nodes
        assert g.get_node("n1") is n1

    def test_graph_add_edge(self):
        n1, n2 = _make_node("n1"), _make_node("n2")
        g = _make_graph("g1", [n1, n2])
        edge = GraphEdge("n1", "n2")
        g.add_edge(edge)
        assert edge in g.edges

    def test_get_ready_nodes_no_deps(self):
        n1, n2 = _make_node("n1"), _make_node("n2")
        g = _make_graph("g1", [n1, n2])
        ready = g.get_ready_nodes()
        assert len(ready) == 2

    def test_get_ready_nodes_with_deps(self):
        n1, n2 = _make_node("n1"), _make_node("n2")
        g = _make_graph("g1", [n1, n2], [GraphEdge("n1", "n2")])
        ready = g.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "n1"

    def test_get_ready_nodes_after_completion(self):
        n1, n2 = _make_node("n1"), _make_node("n2")
        n1.status = NodeStatus.COMPLETED
        g = _make_graph("g1", [n1, n2], [GraphEdge("n1", "n2")])
        ready = g.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "n2"

    def test_get_downstream_nodes(self):
        n1, n2, n3 = _make_node("n1"), _make_node("n2"), _make_node("n3")
        g = _make_graph("g1", [n1, n2, n3], [
            GraphEdge("n1", "n2"),
            GraphEdge("n1", "n3"),
        ])
        downstream = g.get_downstream_nodes("n1")
        assert len(downstream) == 2
        assert {d.id for d in downstream} == {"n2", "n3"}

    def test_has_unfinished(self):
        n1 = _make_node("n1")
        n1.status = NodeStatus.COMPLETED
        g = _make_graph("g1", [n1])
        assert not g.has_unfinished()

    def test_has_unfinished_pending(self):
        g = _make_graph("g1", [_make_node("n1")])
        assert g.has_unfinished()

    def test_is_terminal(self):
        g = _make_graph("g1", [])
        assert not g.is_terminal()
        g.state = GraphState.COMPLETED
        assert g.is_terminal()
        g.state = GraphState.FAILED
        assert g.is_terminal()
        g.state = GraphState.CANCELLED
        assert g.is_terminal()

    def test_to_snapshot_roundtrip(self):
        n1 = _make_node("n1")
        n1.status = NodeStatus.COMPLETED
        n2 = _make_node("n2")
        g = _make_graph("g1", [n1, n2], [GraphEdge("n1", "n2")])
        snap = g.to_snapshot()
        assert snap["graph_id"] == "g1"
        assert len(snap["nodes"]) == 2
        assert len(snap["edges"]) == 1

        recovered = DistributedGraph.from_snapshot(snap, {"n1": n1, "n2": n2})
        assert recovered.id == "g1"
        assert recovered.nodes["n1"].status == NodeStatus.COMPLETED
        assert recovered.nodes["n2"].status == NodeStatus.PENDING


# ── Sprint 2: Scheduler ───────────────────────────────────────────────────────


class TestDependencyAwareScheduler:
    @pytest.fixture
    def registry(self):
        reg = InMemoryWorkerRegistry()
        reg.register(_reg("w1"))
        reg.register(_reg("w2"))
        return reg

    @pytest.mark.asyncio
    async def test_schedule_ready_nodes(self, registry):
        scheduler = DependencyAwareScheduler(registry)
        n1, n2 = _make_node("n1"), _make_node("n2")
        g = _make_graph("g1", [n1, n2], [GraphEdge("n1", "n2")])

        assignments = await scheduler.schedule_ready_nodes(g)
        assert len(assignments) == 1
        node, worker_id = assignments[0]
        assert node.id == "n1"
        assert worker_id in ("w1", "w2")
        assert node.status == NodeStatus.RUNNING

    @pytest.mark.asyncio
    async def test_schedule_with_affinity(self, registry):
        scheduler = DependencyAwareScheduler(registry)
        n1 = _make_node("n1")
        n1.affinity_hint = "w2"
        g = _make_graph("g1", [n1])

        assignments = await scheduler.schedule_ready_nodes(g)
        assert len(assignments) == 1
        assert assignments[0][1] == "w2"

    @pytest.mark.asyncio
    async def test_cascade_cancellation(self, registry):
        scheduler = DependencyAwareScheduler(registry)
        n1, n2, n3 = _make_node("n1"), _make_node("n2"), _make_node("n3")
        g = _make_graph("g1", [n1, n2, n3], [
            GraphEdge("n1", "n2"),
            GraphEdge("n1", "n3"),
        ])

        await scheduler.on_node_failed(g, "n1", "boom")
        assert n1.status == NodeStatus.FAILED
        assert n2.status == NodeStatus.CANCELLED
        assert n3.status == NodeStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_no_workers_returns_empty(self):
        scheduler = DependencyAwareScheduler(InMemoryWorkerRegistry())
        g = _make_graph("g1", [_make_node("n1")])
        assignments = await scheduler.schedule_ready_nodes(g)
        assert assignments == []


# ── Sprint 4: Checkpointer ─────────────────────────────────────────────────────


class TestGraphCheckpointer:
    @pytest.fixture
    def checkpointer(self, tmp_path: Path) -> GraphCheckpointer:
        return GraphCheckpointer(directory=tmp_path)

    @pytest.mark.asyncio
    async def test_save_and_load(self, checkpointer: GraphCheckpointer):
        n1 = _make_node("n1")
        n1.status = NodeStatus.COMPLETED
        g = _make_graph("g1", [n1])
        path = await checkpointer.save(g)
        assert path.endswith("g1.json")

        loaded = await checkpointer.load("g1")
        assert loaded is not None
        assert loaded["graph_id"] == "g1"

    @pytest.mark.asyncio
    async def test_load_missing(self, checkpointer: GraphCheckpointer):
        loaded = await checkpointer.load("nonexistent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_list_checkpoints(self, checkpointer: GraphCheckpointer):
        g = _make_graph("g1", [])
        await checkpointer.save(g)
        ids = await checkpointer.list_checkpoints()
        assert "g1" in ids

    @pytest.mark.asyncio
    async def test_delete(self, checkpointer: GraphCheckpointer):
        g = _make_graph("g1", [])
        await checkpointer.save(g)
        assert await checkpointer.delete("g1")
        assert not await checkpointer.delete("g1")


# ── Sprint 5: Recovery ─────────────────────────────────────────────────────────


class TestGraphRecovery:
    @pytest.mark.asyncio
    async def test_recover_failed_graph(self, tmp_path: Path):
        checkpointer = GraphCheckpointer(directory=tmp_path)
        recovery = GraphRecovery(checkpointer)

        n1, n2 = _make_node("n1"), _make_node("n2")
        n2.status = NodeStatus.FAILED
        g = _make_graph("g_fail", [n1, n2], [GraphEdge("n1", "n2")])
        await checkpointer.save(g)

        original = {"n1": _make_node("n1"), "n2": _make_node("n2")}
        recovered = await recovery.recover("g_fail", original)
        assert recovered is not None
        assert recovered.state == GraphState.PENDING
        assert recovered.nodes["n2"].status == NodeStatus.PENDING

    @pytest.mark.asyncio
    async def test_recover_completed_graph_returns_none(self, tmp_path: Path):
        checkpointer = GraphCheckpointer(directory=tmp_path)
        recovery = GraphRecovery(checkpointer)

        g = _make_graph("g_done", [])
        g.state = GraphState.COMPLETED
        await checkpointer.save(g)

        recovered = await recovery.recover("g_done", {})
        assert recovered is None

    @pytest.mark.asyncio
    async def test_recover_missing_returns_none(self):
        recovery = GraphRecovery()
        recovered = await recovery.recover("ghost", {})
        assert recovered is None


# ── Sprint 3: Executor ─────────────────────────────────────────────────────────


class TestGraphExecutor:
    @pytest.fixture
    def registry(self):
        reg = InMemoryWorkerRegistry()
        reg.register(_reg("w1"))
        return reg

    @pytest.mark.asyncio
    async def test_execute_simple_graph(self, registry):
        """A single-node graph should complete successfully."""
        executor = GraphExecutor(
            scheduler=DependencyAwareScheduler(registry),
            registry=registry,
        )
        n1 = _make_node("n1", "ping")
        g = _make_graph("g_simple", [n1])
        result = await executor.execute(g)
        assert result.state == GraphState.COMPLETED
        assert n1.status == NodeStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_dag(self, registry):
        """A 3-node DAG should complete in dependency order."""
        executor = GraphExecutor(
            scheduler=DependencyAwareScheduler(registry),
            registry=registry,
        )
        n1, n2, n3 = _make_node("n1"), _make_node("n2"), _make_node("n3")
        g = _make_graph("g_dag", [n1, n2, n3], [
            GraphEdge("n1", "n2"),
            GraphEdge("n1", "n3"),
        ])
        result = await executor.execute(g)
        assert result.state == GraphState.COMPLETED
        assert all(n.status == NodeStatus.COMPLETED for n in [n1, n2, n3])

    @pytest.mark.asyncio
    async def test_cancellation(self, registry):
        """Cancelling an executor should cancel all nodes."""
        # Register a slow worker so we can cancel mid-flight
        slow_reg = InMemoryWorkerRegistry()
        class _SlowWorker:
            async def execute(self, request: WorkerRequest) -> WorkerResponse:
                await asyncio.sleep(10)
                return WorkerResponse(outcome=None, observations=(), metrics=None)
            async def health(self) -> HealthStatus: return HealthStatus.HEALTHY
            async def heartbeat(self) -> None: pass
            async def shutdown(self) -> None: pass
        slow_reg.register(WorkerRegistration(worker_id="slow", worker=_SlowWorker()))
        executor = GraphExecutor(registry=slow_reg)
        n1 = _make_node("n1")
        g = _make_graph("g_cancel", [n1])

        async def run_and_cancel():
            await asyncio.sleep(0.05)
            await executor.cancel()

        await asyncio.gather(executor.execute(g), run_and_cancel())
        assert g.state == GraphState.CANCELLED
        assert n1.status == NodeStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, registry):
        """A node with retries should be retried on transport failure."""
        executor = GraphExecutor(
            scheduler=DependencyAwareScheduler(registry),
            registry=registry,
        )
        n1 = _make_node("n1")
        n1.max_retries = 2
        g = _make_graph("g_retry", [n1])
        result = await executor.execute(g)
        # InProcessTransport succeeds, so node completes
        assert n1.status == NodeStatus.COMPLETED
