"""ExecutionContext — Persistence, Crash Recovery, Engine Integration Tests."""

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from core.workflow import (
    ContextManager,
    ExecutionContext,
    WorkflowEngine,
    WorkflowStore,
    recover_active_workflows,
)
from core.workflow.models import StepDefinition, StepStatus, WorkflowStatus


class WorkflowContextTests(unittest.TestCase):
    """Tests for ExecutionContext lifecycle, persistence, and engine integration."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = os.path.join(self._tmpdir, "test_context.db")
        self.store = WorkflowStore(self._db)
        self.engine = WorkflowEngine(self.store)
        self.cm = self.engine.context_manager
        self._patcher = patch("core.tools.execution.execute_tool_block", new_callable=AsyncMock)
        self._mock_exec = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self.engine = None
        self.store = None

    # ── Context Lifecycle ──────────────────────────────────────────────

    def test_01_create_and_get_context(self):
        """Verify context creation and retrieval."""
        ctx = self.cm.create_context(
            workflow_id="wf_test_01",
            owner="dev",
            session_id="sess_01",
            variables={"goal": "build an app", "language": "python"},
            metadata={"source": "test", "priority": 1},
        )
        self.assertEqual(ctx.workflow_id, "wf_test_01")
        self.assertEqual(ctx.variables["goal"], "build an app")
        self.assertEqual(ctx.metadata["priority"], 1)

        loaded = self.cm.get_context("wf_test_01")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.variables["goal"], "build an app")
        self.assertEqual(loaded.metadata["source"], "test")

    def test_02_update_context(self):
        """Verify context updates persist to SQLite."""
        self.cm.create_context("wf_test_02", variables={"x": 1})
        ctx = self.cm.get_context("wf_test_02")
        ctx.variables["x"] = 42
        ctx.variables["y"] = "hello"
        self.cm.update_context(ctx)

        loaded = self.cm.get_context("wf_test_02")
        self.assertEqual(loaded.variables["x"], 42)
        self.assertEqual(loaded.variables["y"], "hello")

    def test_03_delete_context(self):
        """Verify context deletion."""
        self.cm.create_context("wf_test_03")
        self.assertIsNotNone(self.cm.get_context("wf_test_03"))
        self.cm.delete_context("wf_test_03")
        self.assertIsNone(self.cm.get_context("wf_test_03"))

    # ── Context Persists Across Crash/Restart ──────────────────────────

    def test_04_context_survives_store_reinit(self):
        """Verify context persists when store is re-initialized (simulating restart)."""
        self.cm.create_context(
            "wf_restart",
            variables={"build_status": "in_progress", "step": 2},
        )

        store2 = WorkflowStore(self._db)
        cm2 = ContextManager(store2)
        loaded = cm2.get_context("wf_restart")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.variables["step"], 2)
        self.assertEqual(loaded.variables["build_status"], "in_progress")

    # ── Context Created in start_workflow ──────────────────────────────

    def test_05_context_created_on_start(self):
        """Verify start_workflow creates a context automatically."""
        self._mock_exec.return_value = ("bash", {"output": "ok", "exit_code": 0})

        async def _run():
            steps = [StepDefinition(tool_name="bash", input_data={"cmd": "echo"})]
            wf = await self.engine.start_workflow(
                "ctx_test", steps, owner="dev", session_id="s5",
                execution_context={"goal": "hello world"},
            )
            ctx = self.cm.get_context(wf.workflow_id)
            self.assertIsNotNone(ctx)
            self.assertEqual(ctx.owner, "dev")
            self.assertEqual(ctx.session_id, "s5")
            self.assertEqual(ctx.variables["goal"], "hello world")

        asyncio.run(_run())

    # ── Context Available During Step Execution ────────────────────────

    def test_06_context_available_in_tool(self):
        """Verify context is passed to execute_tool_block during step execution."""
        captured = {}

        async def _capture_context(*a, **kw):
            captured["context"] = kw.get("context")
            return ("bash", {"output": "ok", "exit_code": 0})

        self._mock_exec.side_effect = _capture_context

        async def _run():
            steps = [StepDefinition(tool_name="bash", input_data={"cmd": "test"})]
            await self.engine.start_workflow(
                "ctx_available", steps, owner="dev", session_id="s6",
                execution_context={"goal": "verify context"},
            )
            await asyncio.sleep(0.2)
            self.assertIsNotNone(captured.get("context"),
                                 "Context should be passed to execute_tool_block")
            self.assertEqual(captured["context"].variables.get("goal"), "verify context")

        asyncio.run(_run())

    # ── Context Survives Crash Recovery ────────────────────────────────

    def test_07_context_survives_crash_recovery(self):
        """Verify context is preserved and accessible after crash + recovery."""
        self._mock_exec.return_value = ("bash", {"output": "ok", "exit_code": 0})

        async def _phase1():
            steps = [
                StepDefinition(tool_name="bash", input_data={"cmd": "step0"}),
                StepDefinition(tool_name="bash", input_data={"cmd": "step1"}),
            ]
            wf = await self.engine.start_workflow(
                "ctx_crash", steps, owner="dev",
                execution_context={"status": "phase1"},
            )
            wid = wf.workflow_id
            await asyncio.sleep(0.05)

            # Update context variables as if step 0 produced output
            ctx = self.cm.get_context(wid)
            ctx.variables["step0_result"] = "found data"
            ctx.variables["status"] = "phase1_done"
            self.cm.update_context(ctx)

            # Crash the workflow
            task = self.engine._running.get(wid)
            if task:
                task.cancel()
                try:
                    await task
                except Exception:
                    pass
            return wid

        wid = asyncio.run(_phase1())

        # Simulate restart: new engine, same store
        store2 = WorkflowStore(self._db)
        engine2 = WorkflowEngine(store2)
        cm2 = engine2.context_manager

        ctx_before = cm2.get_context(wid)
        self.assertIsNotNone(ctx_before)
        self.assertEqual(ctx_before.variables["step0_result"], "found data")
        self.assertEqual(ctx_before.variables["status"], "phase1_done")

        wf_stale = store2.get_workflow(wid)
        wf_stale.status = WorkflowStatus.RUNNING
        wf_stale.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)
        store2.update_workflow(wf_stale)
        for s in wf_stale.steps:
            s.status = StepStatus.PENDING
            store2.update_step(s)

        async def _phase2():
            recovered = await recover_active_workflows(engine2)
            self.assertGreaterEqual(len(recovered), 1)
            await asyncio.sleep(0.3)

            ctx_after = cm2.get_context(wid)
            self.assertIsNotNone(ctx_after)
            self.assertEqual(ctx_after.variables["step0_result"], "found data",
                             "Context should survive crash recovery")
            self.assertIn("status", ctx_after.variables)

        asyncio.run(_phase2())

    # ── Context Available During Compensation ─────────────────────────

    def test_08_context_available_during_compensation(self):
        """Verify context is available when compensation runs (no regression)."""
        call_idx = [0]

        async def _dispatch(*a, **kw):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 0:
                return ("bash", {"output": "ok", "exit_code": 0})
            if idx == 1:
                return ("bash", {"error": "fail", "exit_code": 1})
            if idx == 2:
                return ("bash", {"output": "compensated", "exit_code": 0})
            return ("bash", {"output": "ok", "exit_code": 0})

        async def _run():
            call_idx[0] = 0
            with patch("core.tools.execution.execute_tool_block",
                       new_callable=AsyncMock) as mock:
                mock.side_effect = _dispatch
                steps = [
                    StepDefinition(tool_name="create", compensation_tool="delete",
                                   compensation_data={"id": "abc"}),
                    StepDefinition(tool_name="send", max_retries=0),
                ]
                wf = await self.engine.start_workflow(
                    "ctx_comp", steps, owner="dev",
                    execution_context={"resource": "test"},
                )
                wid = wf.workflow_id
                await asyncio.sleep(0.3)

                final = self.engine.store.get_workflow(wid)
                self.assertEqual(final.status, WorkflowStatus.COMPENSATED)
                ctx = self.cm.get_context(wid)
                self.assertIsNotNone(ctx)
                self.assertEqual(ctx.variables["resource"], "test",
                                 "Context should survive compensation")

        asyncio.run(_run())

    # ── Context Isolation Between Workflows ───────────────────────────

    def test_09_context_isolation(self):
        """Verify each workflow gets its own isolated context."""
        ctx1 = self.cm.create_context("wf_iso_1", variables={"idx": 1})
        ctx2 = self.cm.create_context("wf_iso_2", variables={"idx": 2})

        ctx1.variables["idx"] = 99
        self.cm.update_context(ctx1)

        loaded1 = self.cm.get_context("wf_iso_1")
        loaded2 = self.cm.get_context("wf_iso_2")
        self.assertEqual(loaded1.variables["idx"], 99)
        self.assertEqual(loaded2.variables["idx"], 2,
                         "Contexts must be isolated")


if __name__ == "__main__":
    unittest.main(verbosity=2)
