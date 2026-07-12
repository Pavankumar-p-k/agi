"""WP-008 Workflow Enhancements: timeout, idempotency enforcement, graph persistence."""

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from core.workflow import ExecutionGraph, ExecutionNode, WorkflowEngine, WorkflowStore
from core.workflow.events import IDEMPOTENCY_HIT
from core.workflow.models import (
    StepDefinition,
    StepStatus,
    WorkflowStatus,
)


class Wp008WorkflowTimeoutTests(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = os.path.join(self._tmpdir, "test_wp008.db")
        self.store = WorkflowStore(self._db)
        self.engine = WorkflowEngine(self.store)
        self._patcher = patch("core.tools.execution.execute_tool_block", new_callable=AsyncMock)
        self._mock_exec = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self.engine = None
        self.store = None

    def _make_slow_step(self) -> StepDefinition:
        return StepDefinition(
            tool_name="bash",
            input_data={"command": "sleep"},
            timeout_seconds=30,
        )

    def test_workflow_timeout_marks_as_failed(self):
        """Workflow-level timeout fires between steps when aggregate exceeds budget."""
        self._mock_exec.return_value = ("bash", {"output": "ok", "exit_code": 0})

        async def _run():
            wf = await self.engine.start_workflow(
                "timeout_test",
                [StepDefinition(tool_name="bash", input_data={"command": "a"}, max_retries=0)
                 for _ in range(100)],
                timeout_seconds=0.1,
            )
            wid = wf.workflow_id
            await asyncio.sleep(0.5)
            wf_final = self.store.get_workflow(wid)
            self.assertEqual(wf_final.status, WorkflowStatus.FAILED)
            events = self.store.get_events(wid)
            timeout_events = [e for e in events if "workflow_timeout" in json.dumps(e.data)]
            self.assertGreaterEqual(len(timeout_events), 1, "Should emit workflow_timeout event")

        asyncio.run(_run())

    def test_step_timeout_raises_on_slow_tool(self):
        """Step-level timeout should abort via asyncio.wait_for."""
        async def _blocking(*_a, **_kw):
            await asyncio.sleep(30)
            return ("bash", {"output": "done", "exit_code": 0})
        self._mock_exec.side_effect = _blocking

        async def _run():
            wf = await self.engine.start_workflow("step_timeout", [
                StepDefinition(tool_name="bash", input_data={"command": "hang"},
                               timeout_seconds=0.05, max_retries=0),
            ])
            wid = wf.workflow_id
            await asyncio.sleep(0.3)
            wf_final = self.store.get_workflow(wid)
            self.assertEqual(wf_final.status, WorkflowStatus.FAILED)
            self.assertEqual(wf_final.steps[0].status, StepStatus.FAILED)

        asyncio.run(_run())


class Wp008IdempotencyTests(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = os.path.join(self._tmpdir, "test_idem.db")
        self.store = WorkflowStore(self._db)
        self.engine = WorkflowEngine(self.store)
        self._patcher = patch("core.tools.execution.execute_tool_block", new_callable=AsyncMock)
        self._mock_exec = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self.engine = None
        self.store = None

    def test_completed_steps_skipped_on_resume(self):
        """On resume, already-COMPLETED steps are skipped without re-execution."""
        call_count = [0]
        async def _side(*_a, **_kw):
            call_count[0] += 1
            return ("bash", {"output": "done", "exit_code": 0})
        self._mock_exec.side_effect = _side

        async def _run():
            wf = await self.engine.start_workflow("idem_test", [
                StepDefinition(tool_name="bash", input_data={"command": "a"},
                               idempotency_key="k1"),
                StepDefinition(tool_name="bash", input_data={"command": "b"},
                               idempotency_key="k2"),
            ])
            wid = wf.workflow_id
            await asyncio.sleep(0.2)

            self.assertEqual(call_count[0], 2)
            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPLETED)

            # Simulate crash after step A but before step B:
            # rewind current_step to 0 but keep step A COMPLETED
            rewind = self.store.get_workflow(wid)
            rewind.current_step = 0
            rewind.status = WorkflowStatus.RUNNING
            rewind.steps[1].status = StepStatus.PENDING
            rewind.steps[1].started_at = None
            rewind.steps[1].completed_at = None
            rewind.steps[1].output_data = None
            rewind.steps[1].error = None
            self.store.update_workflow(rewind)
            for s in rewind.steps:
                self.store.update_step(s)

            # Resume — should skip step A (already COMPLETED) and only execute step B
            call_count[0] = 0
            await self.engine.resume_workflow(wid)
            await asyncio.sleep(0.1)

            self.assertEqual(call_count[0], 1,
                             "Only step B should execute; step A skipped")
            final2 = self.store.get_workflow(wid)
            self.assertEqual(final2.status, WorkflowStatus.COMPLETED)

        asyncio.run(_run())

    def test_failed_step_does_retry_with_idempotency_key(self):
        """A FAILED step with the same idempotency key should retry, not skip."""
        call_count = [0]
        async def _side(*_a, **_kw):
            call_count[0] += 1
            if call_count[0] <= 1:
                return ("bash", {"error": "fail", "exit_code": 1})
            return ("bash", {"output": "ok", "exit_code": 0})
        self._mock_exec.side_effect = _side

        async def _run():
            wf = await self.engine.start_workflow("idem_retry", [
                StepDefinition(tool_name="bash", input_data={"command": "a"},
                               idempotency_key="k_retry", max_retries=1),
            ])
            wid = wf.workflow_id
            await asyncio.sleep(0.2)
            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPLETED)
            self.assertEqual(call_count[0], 2,
                             "Failed step must retry despite idempotency key")

        asyncio.run(_run())


class Wp008ExecutionGraphPersistenceTests(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = os.path.join(self._tmpdir, "test_graph.db")
        self.store = WorkflowStore(self._db)

    def tearDown(self):
        self.store = None

    def _build_graph(self) -> ExecutionGraph:
        g = ExecutionGraph(goal="Build feature X", goal_id="g_feature_x")
        root = ExecutionNode(label="Implement feature X", node_type="goal")
        g.set_root(root)
        n1 = root.add_child(ExecutionNode(label="Design API", node_type="planning"))
        n2 = root.add_child(ExecutionNode(label="Write code", node_type="coding"))
        n1.add_child(ExecutionNode(label="Review spec", node_type="review"))
        n2.add_child(ExecutionNode(label="Write tests", node_type="testing"))
        return g

    def test_save_and_load_round_trip(self):
        g = self._build_graph()
        self.store.save_graph(g)
        loaded = self.store.load_graph("g_feature_x")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.goal, "Build feature X")
        self.assertEqual(loaded.goal_id, "g_feature_x")
        self.assertIsNotNone(loaded.root)
        self.assertEqual(loaded.root.label, "Implement feature X")
        self.assertEqual(len(loaded.root.children), 2)
        child_labels = {c.label for c in loaded.root.children}
        self.assertIn("Design API", child_labels)
        self.assertIn("Write code", child_labels)

    def test_load_nonexistent_returns_none(self):
        loaded = self.store.load_graph("g_nonexistent")
        self.assertIsNone(loaded)

    def test_save_overwrites_existing(self):
        g1 = ExecutionGraph(goal="First", goal_id="g_overwrite")
        g1.set_root(ExecutionNode(label="Root 1"))
        self.store.save_graph(g1)

        g2 = ExecutionGraph(goal="Second", goal_id="g_overwrite")
        g2.set_root(ExecutionNode(label="Root 2"))
        self.store.save_graph(g2)

        loaded = self.store.load_graph("g_overwrite")
        self.assertEqual(loaded.goal, "Second")
        self.assertEqual(loaded.root.label, "Root 2")

    def test_list_graphs(self):
        for i in range(3):
            g = ExecutionGraph(goal=f"Goal {i}", goal_id=f"g_{i}")
            g.set_root(ExecutionNode(label=f"Root {i}"))
            self.store.save_graph(g)

        graphs = self.store.list_graphs(limit=10)
        self.assertEqual(len(graphs), 3)
        goal_ids = [g["goal_id"] for g in graphs]
        self.assertIn("g_0", goal_ids)
        self.assertIn("g_2", goal_ids)

    def test_node_fields_survive_round_trip(self):
        g = ExecutionGraph(goal="Field test", goal_id="g_fields")
        n = ExecutionNode(
            label="Node A",
            node_type="review",
            status="completed",
            confidence=0.95,
            estimate_seconds=120,
            detail="Some detail",
            trust_level="safe",
            can_skip=False,
            can_reorder=False,
        )
        n.files = ["src/a.py"]
        n.artifacts = ["art_1"]
        n.logs = ["log1"]
        n.agent_reasoning = "Because"
        n.error = None
        n.started_at = "2025-01-01T00:00:00"
        n.completed_at = "2025-01-01T01:00:00"
        g.set_root(n)
        self.store.save_graph(g)

        loaded = self.store.load_graph("g_fields")
        root = loaded.root
        self.assertEqual(root.label, "Node A")
        self.assertEqual(root.node_type, "review")
        self.assertEqual(root.status, "completed")
        self.assertEqual(root.confidence, 0.95)
        self.assertEqual(root.estimate_seconds, min(120, 86400))
        self.assertEqual(root.detail, "Some detail")
        self.assertEqual(root.trust_level, "safe")
        self.assertFalse(root.can_skip)
        self.assertFalse(root.can_reorder)
        self.assertEqual(root.files, ["src/a.py"])
        self.assertEqual(root.artifacts, ["art_1"])
        self.assertEqual(root.logs, ["log1"])
        self.assertEqual(root.agent_reasoning, "Because")
        self.assertIsNone(root.error)
        self.assertEqual(root.started_at, "2025-01-01T00:00:00")
        self.assertEqual(root.completed_at, "2025-01-01T01:00:00")
