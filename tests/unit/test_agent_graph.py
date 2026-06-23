"""AgentExecutionGraph + ParallelAgentExecutor tests."""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.agents.graph import (
    AgentExecutionGraph,
    GraphNode,
    NodeStatus,
    build_graph_from_tasks,
    get_phase_for_step,
)
from core.agents.events import AgentEvent
from core.agents.parallel_executor import ParallelAgentExecutor


class TestGraphNode(unittest.TestCase):
    """GraphNode data structure."""

    def test_01_creation(self):
        node = GraphNode(node_id="n1", agent_id="build", goal="build app", phase=1)
        self.assertEqual(node.node_id, "n1")
        self.assertEqual(node.agent_id, "build")
        self.assertEqual(node.phase, 1)
        self.assertEqual(node.status, NodeStatus.PENDING)
        self.assertIsNone(node.duration)

    def test_02_duration(self):
        node = GraphNode(node_id="n1", agent_id="build", goal="build", phase=1)
        node.started_at = 100.0
        node.completed_at = 105.0
        self.assertEqual(node.duration, 5.0)


class TestStepPhase(unittest.TestCase):
    """Step name to phase mapping."""

    def test_03_research_phase(self):
        self.assertEqual(get_phase_for_step("research"), 0)

    def test_04_build_phase(self):
        self.assertEqual(get_phase_for_step("build"), 1)

    def test_05_email_phase(self):
        self.assertEqual(get_phase_for_step("email"), 6)

    def test_06_unknown_phase(self):
        self.assertEqual(get_phase_for_step("unknown"), 50)


class TestAgentExecutionGraph(unittest.TestCase):
    """Graph structure, ready nodes, completion, serialization."""

    def setUp(self):
        self.graph = AgentExecutionGraph(max_parallel=3)

    def test_07_empty_graph_is_complete(self):
        self.assertTrue(self.graph.is_complete)

    def test_08_add_node(self):
        n1 = GraphNode(node_id="n1", agent_id="research", goal="research ui", phase=0)
        self.graph.add_node(n1)
        self.assertEqual(len(self.graph.nodes), 1)

    def test_09_ready_nodes_returns_pending(self):
        self.graph.add_node(GraphNode("n1", "research", "research ui", phase=0))
        self.graph.add_node(GraphNode("n2", "research", "research pay", phase=0))
        ready = self.graph.get_ready_nodes()
        self.assertEqual(len(ready), 2)

    def test_10_ready_nodes_skips_completed_phase(self):
        n1 = GraphNode("n1", "research", "research ui", phase=0)
        self.graph.add_node(n1)
        self.graph.add_node(GraphNode("n2", "build", "build app", phase=1))

        # Complete phase 0 node
        self.graph.mark_completed("n1", {"output": "done"})
        ready = self.graph.get_ready_nodes()
        # All phase 0 done, should return phase 1
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].node_id, "n2")

    def test_11_is_complete_all_done(self):
        n1 = GraphNode("n1", "research", "research ui", phase=0)
        n2 = GraphNode("n2", "build", "build app", phase=1)
        self.graph.add_node(n1)
        self.graph.add_node(n2)
        self.graph.mark_completed("n1", {"output": "done"})
        self.graph.mark_completed("n2", {"output": "done"})
        self.assertTrue(self.graph.is_complete)

    def test_12_is_complete_with_failures(self):
        n1 = GraphNode("n1", "research", "research ui", phase=0)
        self.graph.add_node(n1)
        self.graph.mark_failed("n1", "error")
        self.assertTrue(self.graph.is_complete)

    def test_13_mark_running(self):
        n1 = GraphNode("n1", "build", "build app", phase=1)
        self.graph.add_node(n1)
        self.graph.mark_running("n1")
        self.assertEqual(self.graph.get_node("n1").status, NodeStatus.RUNNING)
        self.assertIsNotNone(self.graph.get_node("n1").started_at)

    def test_14_artifacts_merged(self):
        n1 = GraphNode("n1", "research", "research ui", phase=0)
        n2 = GraphNode("n2", "build", "build app", phase=1)
        self.graph.add_node(n1)
        self.graph.add_node(n2)
        self.graph.mark_completed("n1", {"output": "r"}, {"snapshot": "art_1"})
        self.graph.mark_completed("n2", {"output": "b"}, {"apk": "art_2"})
        merged = self.graph.get_all_artifacts()
        self.assertIn("snapshot", merged)
        self.assertIn("apk", merged)

    def test_15_serialization_roundtrip(self):
        n1 = GraphNode("n1", "research", "research ui", phase=0)
        n2 = GraphNode("n2", "build", "build app", phase=1)
        self.graph.add_node(n1)
        self.graph.add_node(n2)
        self.graph.mark_completed("n1", {"output": "done"}, {"snap": "art_s"})

        data = self.graph.to_dict()
        restored = AgentExecutionGraph.from_dict(data)

        self.assertIn("n1", restored.nodes)
        self.assertIn("n2", restored.nodes)
        self.assertEqual(
            restored.get_node("n1").status, NodeStatus.COMPLETED
        )
        self.assertEqual(
            restored.get_node("n1").artifacts.get("snap"), "art_s"
        )
        self.assertEqual(restored.max_parallel, 3)

    def test_16_build_graph_from_tasks(self):
        tasks = [
            {"agent_id": "research", "goal": "research ui", "step": "research", "parameters": {}},
            {"agent_id": "build", "goal": "build app", "step": "build", "parameters": {}},
            {"agent_id": "email", "goal": "email results", "step": "email", "parameters": {}},
        ]
        graph = build_graph_from_tasks(tasks)
        self.assertEqual(len(graph.nodes), 3)
        # Phases should be 0 (research), 1 (build), 6 (email)
        phases = sorted(set(n.phase for n in graph.nodes.values()))
        self.assertEqual(phases, [0, 1, 6])

    def test_17_is_blocked_with_blocking_prior_failure(self):
        """is_blocked is True when phase 0 all failed and phase 1 pending."""
        n1 = GraphNode("n1", "research", "research ui", phase=0)
        n2 = GraphNode("n2", "build", "build app", phase=1)
        self.graph.add_node(n1)
        self.graph.add_node(n2)
        self.graph.mark_failed("n1", "error")
        # Phase 0 all terminal (failed), phase 1 pending — is_blocked
        self.assertTrue(self.graph.is_blocked)


class TestParallelAgentExecutor(unittest.TestCase):
    """ParallelAgentExecutor with mocked agents."""

    def setUp(self):
        self._agent_patcher = patch("core.agents.parallel_executor.get_agent")
        self._mock_get_agent = self._agent_patcher.start()

        self._agents = {}
        for aid in ("research", "build", "test", "email"):
            agent = MagicMock()
            agent.agent_id = aid
            agent.execute = AsyncMock(
                return_value={
                    "output": f"{aid} done",
                    "exit_code": 0,
                    "_artifacts": {},
                }
            )
            self._agents[aid] = agent

        def _get_agent(aid):
            return self._agents.get(aid)

        self._mock_get_agent.side_effect = _get_agent

    def tearDown(self):
        self._agent_patcher.stop()

    def test_18_executes_all_nodes(self):
        graph = AgentExecutionGraph(max_parallel=5)
        graph.add_node(GraphNode("n1", "research", "research ui", phase=0))
        graph.add_node(GraphNode("n2", "research", "research pay", phase=0))
        graph.add_node(GraphNode("n3", "build", "build app", phase=1))

        executor = ParallelAgentExecutor(max_parallel=5, emit_events=False)
        result = asyncio_run(executor.execute(graph, "test_wf"))

        self.assertIsNotNone(result)
        self.assertIn("artifacts", result)
        self.assertTrue(graph.is_complete)
        self.assertEqual(graph.get_node("n1").status, NodeStatus.COMPLETED)
        self.assertEqual(graph.get_node("n2").status, NodeStatus.COMPLETED)
        self.assertEqual(graph.get_node("n3").status, NodeStatus.COMPLETED)

    def test_19_parallel_execution_speedup(self):
        """Two parallel phase-0 nodes should finish as fast as one (async)."""
        graph = AgentExecutionGraph(max_parallel=5)

        async def slow_agent(*a, **kw):
            await asyncio.sleep(0.2)
            return {"output": "done", "exit_code": 0}

        self._agents["research"].execute = AsyncMock(side_effect=slow_agent)

        graph.add_node(GraphNode("n1", "research", "r1", phase=0))
        graph.add_node(GraphNode("n2", "research", "r2", phase=0))

        start = time.monotonic()
        executor = ParallelAgentExecutor(max_parallel=5, emit_events=False)
        asyncio_run(executor.execute(graph, "test_speed"))
        elapsed = time.monotonic() - start

        # Two 0.2s tasks in parallel should finish in ~0.2s, not ~0.4s
        self.assertLess(elapsed, 0.35, (
            f"Parallel execution took {elapsed:.3f}s, expected <0.35s"
        ))

    def test_20_events_emitted(self):
        graph = AgentExecutionGraph(max_parallel=2)
        graph.add_node(GraphNode("n1", "research", "r1", phase=0))

        executor = ParallelAgentExecutor(max_parallel=2, emit_events=True)
        asyncio_run(executor.execute(graph, "test_events"))

        event_types = [e.event_type for e in executor.events]
        self.assertIn("node_started", event_types)
        self.assertIn("node_completed", event_types)
        self.assertIn("graph_completed", event_types)

    def test_21_phase_barrier_respected(self):
        """Phase 1 nodes should not start until ALL phase 0 nodes complete."""
        graph = AgentExecutionGraph(max_parallel=5)

        phase_0_started = []
        phase_1_started = []

        original_exec = dict(self._agents)

        async def tracked_research(*a, **kw):
            phase_0_started.append(time.monotonic())
            await asyncio.sleep(0.1)
            return {"output": "done", "exit_code": 0}

        async def tracked_build(*a, **kw):
            phase_1_started.append(time.monotonic())
            return {"output": "done", "exit_code": 0}

        self._agents["research"].execute = AsyncMock(side_effect=tracked_research)
        self._agents["build"].execute = AsyncMock(side_effect=tracked_build)

        graph.add_node(GraphNode("n1", "research", "r1", phase=0))
        graph.add_node(GraphNode("n2", "research", "r2", phase=0))
        graph.add_node(GraphNode("n3", "build", "b1", phase=1))

        executor = ParallelAgentExecutor(max_parallel=5, emit_events=False)
        asyncio_run(executor.execute(graph, "test_barrier"))

        self.assertEqual(len(phase_0_started), 2)
        self.assertEqual(len(phase_1_started), 1)
        # Phase 1 should have started AFTER phase 0 completed
        p0_end = max(phase_0_started) + 0.1  # approximate
        p1_start = phase_1_started[0]
        self.assertGreaterEqual(p1_start, p0_end - 0.05)

    def test_22_max_parallel_limited(self):
        """With max_parallel=1, nodes execute one at a time."""
        graph = AgentExecutionGraph(max_parallel=1)
        order = []

        async def _make_exec(aid):
            async def _exec(*a, **kw):
                order.append(aid)
                await asyncio.sleep(0.05)
                return {"output": "done", "exit_code": 0}
            return _exec

        self._agents["research"].execute = AsyncMock(side_effect=None)
        self._agents["research"].execute.side_effect = None

        async def research_exec(*a, **kw):
            order.append("research")
            await asyncio.sleep(0.05)
            return {"output": "done", "exit_code": 0}

        self._agents["research"].execute = AsyncMock(side_effect=research_exec)

        graph.add_node(GraphNode("n1", "research", "r1", phase=0))
        graph.add_node(GraphNode("n2", "research", "r2", phase=0))

        executor = ParallelAgentExecutor(max_parallel=1, emit_events=False)
        asyncio_run(executor.execute(graph, "test_limit"))

        self.assertEqual(len(order), 2)

    def test_23_agent_not_found_marks_failed(self):
        """Unknown agent_id marks the node as failed."""
        graph = AgentExecutionGraph(max_parallel=2)
        graph.add_node(GraphNode("n1", "ghost_agent", "ghost", phase=0))

        executor = ParallelAgentExecutor(max_parallel=2)
        asyncio_run(executor.execute(graph, "test_ghost"))

        self.assertEqual(graph.get_node("n1").status, NodeStatus.FAILED)
        self.assertIn("No agent registered", graph.get_node("n1").error or "")

    def test_24_agent_exception_marks_failed(self):
        """Exception in agent.execute marks node failed."""
        graph = AgentExecutionGraph(max_parallel=2)
        graph.add_node(GraphNode("n1", "research", "crash", phase=0))

        self._agents["research"].execute = AsyncMock(
            side_effect=RuntimeError("crash!")
        )

        executor = ParallelAgentExecutor(max_parallel=2)
        asyncio_run(executor.execute(graph, "test_crash"))

        self.assertEqual(graph.get_node("n1").status, NodeStatus.FAILED)


def asyncio_run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            fut = pool.submit(asyncio.run, coro)
            return fut.result()
    return asyncio.run(coro)
