"""Workflow Engine v1 — Failure Mode Validation Tests

Tests the WorkflowEngine's durability logic: crash recovery, idempotency,
cancellation, and concurrency. Mocks execute_tool_block to avoid
depending on external tool execution (Docker, shell, etc.).
"""

import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from core.workflow import WorkflowEngine, WorkflowStore, recover_active_workflows
from core.workflow.models import (
    StepDefinition, StepStatus, WorkflowInstance, WorkflowStatus,
)


class WorkflowFailureModeTests(unittest.TestCase):
    """Tests for production durability: crash, side-effect, cancel, concurrent."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = os.path.join(self._tmpdir, "test_workflow.db")
        self.store = WorkflowStore(self._db)
        self.engine = WorkflowEngine(self.store)
        self._patcher = patch("core.tools.execution.execute_tool_block", new_callable=AsyncMock)
        self._mock_exec = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self.engine = None
        self.store = None

    def _make_steps(self, count: int = 3) -> list[StepDefinition]:
        return [StepDefinition(tool_name="bash", input_data={"command": "echo ok"},
                               timeout_seconds=5, max_retries=1) for _ in range(count)]

    def _get_sqlite_records(self, table: str) -> list:
        import sqlite3
        with sqlite3.connect(self._db) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]

    # ── Test 1: Mid-Step Crash / Recovery ────────────────────────────────

    def test_01_mid_step_crash_recovery(self):
        """Simulate crash mid-step 1, recover, verify step 1 resumes (not skipped)."""
        self._mock_exec.return_value = ("bash", {"output": "done", "exit_code": 0})

        async def _run():
            wf = await self.engine.start_workflow("crash_test", self._make_steps(3))
            wid = wf.workflow_id

            await asyncio.sleep(0.05)
            task = self.engine._running.get(wid)
            if task:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

            wf_after = self.store.get_workflow(wid)
            self.assertEqual(wf_after.steps[0].status, StepStatus.COMPLETED,
                             "Step 0 should complete before crash")
            self.assertGreaterEqual(wf_after.current_step, 1,
                                    "Current step should advance")

            wf_after.status = WorkflowStatus.RUNNING
            wf_after.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)
            self.store.update_workflow(wf_after)
            self.assertTrue(wf_after.is_stale)

            recovered = await recover_active_workflows(self.engine)
            self.assertGreaterEqual(len(recovered), 1)
            await asyncio.sleep(0.2)

            wf_final = self.store.get_workflow(wid)
            self.assertEqual(wf_final.status, WorkflowStatus.COMPLETED)
            self.assertEqual(wf_final.current_step, 3)
            for i, s in enumerate(wf_final.steps):
                self.assertEqual(s.status, StepStatus.COMPLETED, f"Step {i}")

        asyncio.run(_run())

    # ── Test 2: Idempotency ──────────────────────────────────────────────

    def test_02_step_does_not_rerun_on_resume(self):
        """Completed steps must NOT re-execute on resume."""
        self._mock_exec.return_value = ("bash", {"output": "done", "exit_code": 0})

        async def _run():
            wf = await self.engine.start_workflow("idempotency_test", self._make_steps(2))
            wid = wf.workflow_id
            await asyncio.sleep(0.1)
            self.assertEqual(self.store.get_workflow(wid).status, WorkflowStatus.COMPLETED)

            completed_ids = [s.step_id for s in self.store.get_workflow(wid).steps
                            if s.status == StepStatus.COMPLETED]

            await self.engine.resume_workflow(wid)
            await asyncio.sleep(0.1)

            final = self.store.get_workflow(wid)
            self.assertEqual([s.step_id for s in final.steps if s.status == StepStatus.COMPLETED],
                             completed_ids, "Completed steps must not re-execute")

        asyncio.run(_run())

    # ── Test 3: Step failure stops workflow ──────────────────────────────

    def test_03_step_failure_does_not_skip_remaining(self):
        """When a step fails, remaining steps must NOT execute."""
        call_count = [0]  # mutable container for closure access
        async def _side_effect(*a, **kw):
            call_count[0] += 1
            if call_count[0] <= 1:
                return ("bash", {"output": "ok", "exit_code": 0})
            return ("bash", {"error": "fail", "exit_code": 1})
        self._mock_exec.side_effect = _side_effect

        async def _run():
            wf = await self.engine.start_workflow("fail_test", self._make_steps(3))
            wid = wf.workflow_id
            await asyncio.sleep(0.2)

            wf_final = self.store.get_workflow(wid)
            self.assertEqual(wf_final.status, WorkflowStatus.FAILED,
                             "Workflow should fail")
            self.assertEqual(wf_final.steps[0].status, StepStatus.COMPLETED)
            self.assertEqual(wf_final.steps[1].status, StepStatus.FAILED,
                             "Step 2 should FAILED")
            self.assertNotEqual(wf_final.steps[2].status, StepStatus.COMPLETED,
                                "Step 3 must NOT run after failure")

        asyncio.run(_run())

    # ── Test 4: Cancellation During Execution ────────────────────────────

    def test_04_cancel_during_execution(self):
        """Cancel a running workflow, verify no zombie steps."""
        async def _blocking(*a, **kw):
            await asyncio.sleep(30)
            return ("bash", {"output": "done", "exit_code": 0})
        self._mock_exec.side_effect = _blocking

        async def _run():
            wf = await self.engine.start_workflow("cancel_test", [
                StepDefinition(tool_name="bash", input_data={"command": "sleep"}, timeout_seconds=60)
            ])
            wid = wf.workflow_id
            await asyncio.sleep(0.05)

            cancelled = await self.engine.cancel_workflow(wid)
            self.assertIsNotNone(cancelled)
            self.assertEqual(cancelled.status, WorkflowStatus.CANCELLED)
            self.assertNotIn(wid, self.engine._running)

            await asyncio.sleep(0.05)
            self.assertEqual(self.store.get_workflow(wid).status, WorkflowStatus.CANCELLED)
            resumed = await self.engine.resume_workflow(wid)
            self.assertEqual(resumed.status, WorkflowStatus.CANCELLED)

        asyncio.run(_run())

    # ── Test 5: Concurrent Workflows ─────────────────────────────────────

    def test_05_concurrent_workflows(self):
        """Launch 4 concurrent workflows, verify SQLite consistency."""
        self._mock_exec.return_value = ("bash", {"output": "done", "exit_code": 0})

        async def _run():
            wfs = await asyncio.gather(*[
                self.engine.start_workflow(f"concurrent_{i}", self._make_steps(2))
                for i in range(4)
            ])
            self.assertEqual(len(wfs), 4)
            await asyncio.sleep(0.3)

            for wf in wfs:
                final = self.store.get_workflow(wf.workflow_id)
                self.assertEqual(final.status, WorkflowStatus.COMPLETED)
                for i, s in enumerate(final.steps):
                    self.assertEqual(s.status, StepStatus.COMPLETED, f"wf {wf.workflow_id} step {i}")

            records = self._get_sqlite_records("workflow_instances")
            self.assertEqual(len(records), 4)
            self.assertEqual(len(records), len(set(r["workflow_id"] for r in records)),
                             "No duplicate IDs")

            events = self._get_sqlite_records("workflow_events")
            self.assertGreaterEqual(len(events), 24, "Min 6 events × 4 workflows")

        asyncio.run(_run())

    # ── Test 6: Recovery skips live workflows ────────────────────────────

    def test_06_recovery_skips_live_workflows(self):
        """Workflows with recent heartbeats should NOT be recovered."""
        self._mock_exec.return_value = ("bash", {"output": "done", "exit_code": 0})

        async def _run():
            wf = await self.engine.start_workflow("live_test", self._make_steps(1))
            wid = wf.workflow_id
            await asyncio.sleep(0.05)

            wf_live = self.store.get_workflow(wid)
            wf_live.status = WorkflowStatus.RUNNING
            wf_live.last_heartbeat = datetime.utcnow()
            self.store.update_workflow(wf_live)
            self.assertFalse(wf_live.is_stale)

            recovered = await recover_active_workflows(self.engine)
            self.assertFalse(any(r["workflow_id"] == wid for r in recovered),
                             "Live workflow not recovered")

            wf_live.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)
            self.store.update_workflow(wf_live)
            self.assertTrue(wf_live.is_stale)

            recovered2 = await recover_active_workflows(self.engine)
            self.assertTrue(any(r["workflow_id"] == wid for r in recovered2),
                            "Aged workflow recovered")

        asyncio.run(_run())

    # ── Test 7: Event persistence ────────────────────────────────────────

    def test_07_event_persistence(self):
        """Verify every step transition creates an event."""
        self._mock_exec.return_value = ("bash", {"output": "done", "exit_code": 0})

        async def _run():
            wf = await self.engine.start_workflow("event_test", self._make_steps(2))
            wid = wf.workflow_id
            await asyncio.sleep(0.3)

            event_types = [e.event_type for e in self.store.get_events(wid)]
            for et in ["workflow_started", "step_started", "step_completed",
                       "step_started", "step_completed", "workflow_completed"]:
                self.assertIn(et, event_types, f"Event {et} should exist")
            self.assertGreaterEqual(len(event_types), 6)

        asyncio.run(_run())


    # ═══════════════════════════════════════════════════════════════════
    #  Compensation / Transaction Layer Tests
    # ═══════════════════════════════════════════════════════════════════

    def test_08_compensation_runs_on_step_failure(self):
        """Verify compensation_tool is called when a later step fails."""
        call_idx = [0]

        async def _dispatch(*a, **kw):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 0:
                return ("bash", {"output": "ok", "exit_code": 0})
            if idx == 1:
                return ("bash", {"error": "step failed", "exit_code": 1})
            if idx == 2:
                return ("bash", {"output": "compensated", "exit_code": 0})
            return ("bash", {"output": "ok", "exit_code": 0})

        self._mock_exec.side_effect = None

        async def _run():
            call_idx[0] = 0
            with patch("core.tools.execution.execute_tool_block",
                       new_callable=AsyncMock) as mock:
                mock.side_effect = _dispatch
                steps = [
                    StepDefinition(tool_name="create_reminder",
                                   input_data={"text": "hello"},
                                   compensation_tool="delete_reminder",
                                   compensation_data={"id": "abc"}),
                    StepDefinition(tool_name="send_email",
                                   input_data={"to": "user@example.com"},
                                   max_retries=0),
                ]
                wf = await self.engine.start_workflow("comp_test_1", steps)
                wid = wf.workflow_id
                await asyncio.sleep(0.3)

                final = self.store.get_workflow(wid)
                self.assertEqual(final.status, WorkflowStatus.COMPENSATED,
                                 "Workflow should be COMPENSATED after compensation")
                self.assertEqual(final.steps[0].status, StepStatus.COMPLETED)
                self.assertEqual(final.steps[1].status, StepStatus.FAILED)
                self.assertTrue(final.steps[0].compensated,
                                "Step 0 should be marked compensated")
                self.assertGreaterEqual(call_idx[0], 3,
                                        "Compensation tool should have been called")

        asyncio.run(_run())

    def test_09_no_compensation_when_no_compensation_tool(self):
        """Verify workflow FAILED (not COMPENSATED) when no compensation_tool set."""
        call_idx = [0]

        async def _dispatch(*a, **kw):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 0:
                return ("bash", {"output": "ok", "exit_code": 0})
            return ("bash", {"error": "fail", "exit_code": 1})

        async def _run():
            call_idx[0] = 0
            self._mock_exec.side_effect = _dispatch
            steps = [
                StepDefinition(tool_name="step_a", input_data={"x": 1}),
                StepDefinition(tool_name="step_b", input_data={"y": 2}),
            ]
            wf = await self.engine.start_workflow("comp_test_2", steps)
            wid = wf.workflow_id
            await asyncio.sleep(0.3)

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.FAILED,
                             "Workflow should FAILED (no compensation available)")

        asyncio.run(_run())

    def test_10_compensation_reverse_order(self):
        """Verify compensations run in reverse order of steps."""
        order = []
        call_idx = [0]

        async def _dispatch(*a, **kw):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx < 3:
                return ("bash", {"output": "ok", "exit_code": 0})
            if idx == 3:
                return ("bash", {"error": "fail", "exit_code": 1})
            if idx == 4:
                order.append("comp_C")
                return ("bash", {"output": "ok", "exit_code": 0})
            if idx == 5:
                order.append("comp_B")
                return ("bash", {"output": "ok", "exit_code": 0})
            if idx == 6:
                order.append("comp_A")
                return ("bash", {"output": "ok", "exit_code": 0})
            return ("bash", {"output": "ok", "exit_code": 0})

        async def _run():
            call_idx[0] = 0
            self._mock_exec.side_effect = _dispatch
            steps = [
                StepDefinition(tool_name="s0", compensation_tool="c0", compensation_data={"idx": 0}),
                StepDefinition(tool_name="s1", compensation_tool="c1", compensation_data={"idx": 1}),
                StepDefinition(tool_name="s2", compensation_tool="c2", compensation_data={"idx": 2}),
                StepDefinition(tool_name="s3", input_data={"fail": True}, max_retries=0),
            ]
            wf = await self.engine.start_workflow("comp_test_3", steps)
            wid = wf.workflow_id
            await asyncio.sleep(0.3)

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPENSATED)
            self.assertEqual(order, ["comp_C", "comp_B", "comp_A"],
                             "Compensations must run in reverse step order")
            self.assertTrue(all(s.compensated for s in final.steps[:3]),
                            "Steps 0-2 should be compensated")

        asyncio.run(_run())

    def test_11_compensation_failure(self):
        """Verify COMPENSATION_FAILED when a compensation tool fails."""
        call_idx = [0]

        async def _dispatch(*a, **kw):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 0:
                return ("bash", {"output": "ok", "exit_code": 0})
            if idx == 1:
                return ("bash", {"error": "fail", "exit_code": 1})
            if idx == 2:
                return ("bash", {"error": "compensation failed", "exit_code": 1})
            return ("bash", {"output": "ok", "exit_code": 0})

        async def _run():
            call_idx[0] = 0
            self._mock_exec.side_effect = _dispatch
            steps = [
                StepDefinition(tool_name="s0", compensation_tool="c0"),
                StepDefinition(tool_name="s1", max_retries=0),
            ]
            wf = await self.engine.start_workflow("comp_test_4", steps)
            wid = wf.workflow_id
            await asyncio.sleep(0.3)

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPENSATION_FAILED,
                             "Workflow should be COMPENSATION_FAILED")
            self.assertFalse(final.steps[0].compensated,
                             "Step 0 should NOT be compensated")
            self.assertNotIn(final.steps[0].step_id, final.compensated_steps,
                             "Compensation failure should NOT add step to compensated_steps")

        asyncio.run(_run())

    def test_12_compensating_recovery(self):
        """Simulate crash mid-compensation, recover, verify compensation completes."""
        call_idx_1 = [0]

        async def _dispatch_p1(*a, **kw):
            idx = call_idx_1[0]
            call_idx_1[0] += 1
            if idx == 0:
                return ("bash", {"output": "ok", "exit_code": 0})
            if idx == 1:
                return ("bash", {"error": "fail", "exit_code": 1})
            if idx == 2:
                return ("bash", {"output": "compensated", "exit_code": 0})
            return ("bash", {"output": "ok", "exit_code": 0})

        async def _phase1():
            call_idx_1[0] = 0
            with patch("core.tools.execution.execute_tool_block",
                       new_callable=AsyncMock) as mock:
                mock.side_effect = _dispatch_p1
                steps = [
                    StepDefinition(tool_name="s0", compensation_tool="c0"),
                    StepDefinition(tool_name="s1", max_retries=0),
                ]
                wf = await self.engine.start_workflow("comp_test_5", steps)
                wid = wf.workflow_id
                await asyncio.sleep(0.05)

                task = self.engine._running.get(wid)
                if task:
                    task.cancel()
                    try: await task
                    except Exception: pass

                wf_after = self.store.get_workflow(wid)
                return wid, wf_after.status

        wid, status = asyncio.run(_phase1())

        wf_before = self.store.get_workflow(wid)
        if wf_before.status == WorkflowStatus.COMPENSATED:
            self.assertTrue(True, "Compensation completed before crash")
            return

        self.assertEqual(wf_before.status, WorkflowStatus.COMPENSATING,
                         "Workflow should be in COMPENSATING state")
        wf_before.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)
        self.store.update_workflow(wf_before)

        call_idx_2 = [0]

        async def _dispatch_p2(*a, **kw):
            idx = call_idx_2[0]
            call_idx_2[0] += 1
            if idx == 0:
                return ("bash", {"output": "compensated", "exit_code": 0})
            return ("bash", {"output": "ok", "exit_code": 0})

        async def _phase2():
            call_idx_2[0] = 0
            with patch("core.tools.execution.execute_tool_block",
                       new_callable=AsyncMock) as mock:
                mock.side_effect = _dispatch_p2
                recovered = await recover_active_workflows(self.engine)
                self.assertGreaterEqual(len(recovered), 1)
                await asyncio.sleep(0.2)

                final = self.store.get_workflow(wid)
                self.assertEqual(final.status, WorkflowStatus.COMPENSATED,
                                 "After recovery, workflow should be COMPENSATED")
                self.assertTrue(final.steps[0].compensated)

        asyncio.run(_phase2())

    def test_13_cancel_during_compensation(self):
        """Cancel workflow while compensation is running, verify CANCELLED."""
        started = []
        call_idx = [0]

        async def _dispatch(*a, **kw):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 0:
                return ("bash", {"output": "ok", "exit_code": 0})
            if idx == 1:
                return ("bash", {"error": "fail", "exit_code": 1})
            if idx == 2:
                started.append(True)
                await asyncio.sleep(30)
                return ("bash", {"output": "ok", "exit_code": 0})
            return ("bash", {"output": "ok", "exit_code": 0})

        async def _run():
            call_idx[0] = 0
            with patch("core.tools.execution.execute_tool_block",
                       new_callable=AsyncMock) as mock:
                mock.side_effect = _dispatch
                steps = [
                    StepDefinition(tool_name="s0", compensation_tool="c0"),
                    StepDefinition(tool_name="s1", max_retries=0),
                ]
                wf = await self.engine.start_workflow("comp_test_6", steps)
                wid = wf.workflow_id
                await asyncio.sleep(0.1)

                self.assertTrue(len(started) > 0,
                                "Compensation should have started")
                cancelled = await self.engine.cancel_workflow(wid)
                self.assertIsNotNone(cancelled)
                await asyncio.sleep(0.1)

                final = self.store.get_workflow(wid)
                self.assertEqual(final.status, WorkflowStatus.CANCELLED,
                                 "Cancel during compensation should produce CANCELLED")

        asyncio.run(_run())


    # ═══════════════════════════════════════════════════════════════════
    #  Timeout Enforcement Tests
    # ═══════════════════════════════════════════════════════════════════

    def test_14_step_timeout_enforcement(self):
        """Verify a step fails when timeout_seconds is exceeded."""
        async def _blocking(*a, **kw):
            await asyncio.sleep(30)
            return ("bash", {"output": "done", "exit_code": 0})
        self._mock_exec.side_effect = _blocking

        async def _run():
            steps = [StepDefinition(tool_name="bash", input_data={"command": "sleep"},
                                    timeout_seconds=0.05, max_retries=1)]
            wf = await self.engine.start_workflow("timeout_test", steps)
            wid = wf.workflow_id
            await asyncio.sleep(0.3)

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.FAILED,
                             "Workflow should FAILED on timeout")
            self.assertEqual(final.steps[0].status, StepStatus.FAILED,
                             "Step should FAILED on timeout")

        asyncio.run(_run())

    def test_15_no_timeout_when_not_set(self):
        """Verify step runs normally without timeout_seconds."""
        self._mock_exec.return_value = ("bash", {"output": "done", "exit_code": 0})

        async def _run():
            steps = [StepDefinition(tool_name="bash", input_data={"command": "echo ok"})]
            wf = await self.engine.start_workflow("no_timeout_test", steps)
            wid = wf.workflow_id
            await asyncio.sleep(0.2)

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPLETED,
                             "Workflow should complete normally")

        asyncio.run(_run())

    # ═══════════════════════════════════════════════════════════════════
    #  Retry Budget Tests
    # ═══════════════════════════════════════════════════════════════════

    def test_16_retry_budget_honored(self):
        """Verify workflow stops retrying when retry_budget is exceeded."""
        call_count = [0]
        async def _failing(*a, **kw):
            call_count[0] += 1
            return ("bash", {"error": "fail", "exit_code": 1})
        self._mock_exec.side_effect = _failing

        async def _run():
            steps = [StepDefinition(tool_name="bash", input_data={"command": "fail"},
                                    max_retries=5)]
            wf = await self.engine.start_workflow("budget_test", steps, retry_budget=1)
            wid = wf.workflow_id
            await asyncio.sleep(0.3)

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.FAILED,
                             "Workflow should FAILED")
            self.assertLessEqual(final.retry_count, 2,
                                 "Retry count should be <= 2 (budget of 1 retry + initial)")
            self.assertLessEqual(call_count[0], 2,
                                 "Step should execute at most 2 times (initial + 1 retry)")

        asyncio.run(_run())

    def test_17_retry_budget_unlimited_by_default(self):
        """Verify default retry_budget=0 means unlimited retries."""
        call_count = [0]
        async def _failing(*a, **kw):
            call_count[0] += 1
            if call_count[0] < 3:
                return ("bash", {"error": "fail", "exit_code": 1})
            return ("bash", {"output": "ok", "exit_code": 0})
        self._mock_exec.side_effect = _failing

        async def _run():
            steps = [StepDefinition(tool_name="bash", input_data={"command": "fail"},
                                    max_retries=5)]
            wf = await self.engine.start_workflow("unlimited_budget_test", steps)
            wid = wf.workflow_id
            await asyncio.sleep(0.3)

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPLETED,
                             "Workflow should COMPLETED after retries succeed")
            self.assertEqual(call_count[0], 3,
                             "Step should execute 3 times (initial + 2 retries)")

        asyncio.run(_run())

    # ═══════════════════════════════════════════════════════════════════
    #  Heartbeat Monitor Tests
    # ═══════════════════════════════════════════════════════════════════

    def test_18_heartbeat_monitor_recovers_stale(self):
        """Verify HeartbeatMonitor detects and recovers stale workflows."""
        self._mock_exec.return_value = ("bash", {"output": "done", "exit_code": 0})

        async def _run():
            from core.workflow.heartbeat_monitor import HeartbeatMonitor

            wf = await self.engine.start_workflow("hb_test", self._make_steps(2))
            wid = wf.workflow_id
            await asyncio.sleep(0.05)

            task = self.engine._running.get(wid)
            if task:
                task.cancel()
                try: await task
                except Exception: pass

            wf_stale = self.store.get_workflow(wid)
            wf_stale.status = WorkflowStatus.RUNNING
            wf_stale.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)
            wf_stale.current_step = 0
            self.store.update_workflow(wf_stale)
            for s in wf_stale.steps:
                s.status = StepStatus.PENDING
                self.store.update_step(s)

            hb = HeartbeatMonitor(self.engine, interval=0.05, stale_seconds=30)
            await hb.start()
            await asyncio.sleep(0.5)
            await hb.stop()

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPLETED,
                             "HeartbeatMonitor should recover stale workflow")

        asyncio.run(_run())

    def test_19_heartbeat_monitor_skips_live(self):
        """Verify HeartbeatMonitor does NOT recover workflows with recent heartbeats."""
        self._mock_exec.return_value = ("bash", {"output": "done", "exit_code": 0})

        async def _run():
            from core.workflow.heartbeat_monitor import HeartbeatMonitor

            wf = await self.engine.start_workflow("hb_live_test", self._make_steps(1))
            wid = wf.workflow_id
            await asyncio.sleep(0.1)

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPLETED)

            hb = HeartbeatMonitor(self.engine, interval=0.05, stale_seconds=30)
            await hb.start()
            await asyncio.sleep(0.15)
            await hb.stop()

            self.assertEqual(self.store.get_workflow(wid).status, WorkflowStatus.COMPLETED)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main(verbosity=2)
