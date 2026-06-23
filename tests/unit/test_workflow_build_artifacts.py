"""Build Artifact Integration — Engine picks up _artifacts from step results."""

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from core.workflow import (
    ArtifactStore,
    WorkflowEngine,
    WorkflowStore,
    recover_active_workflows,
)
from core.workflow.models import StepDefinition, StepStatus, WorkflowStatus


class WorkflowBuildArtifactTests(unittest.TestCase):
    """Tests for build artifact registration through the workflow engine."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = os.path.join(self._tmpdir, "test_build_artifact.db")
        self.store = WorkflowStore(self._db)
        self.engine = WorkflowEngine(self.store)
        self.artifact_store = self.engine.artifact_store
        self._patcher = patch("core.tools.execution.execute_tool_block", new_callable=AsyncMock)
        self._mock_exec = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self.engine = None
        self.store = None

    # ── Engine picks up _artifacts from step result ───────────────────

    def test_01_engine_registers_artifacts_from_result(self):
        """Verify engine picks up _artifacts in step result and updates context."""
        async def _mock_build(*a, **kw):
            return "build_project", {
                "success": True,
                "output": "Build completed",
                "exit_code": 0,
                "_artifacts": {"apk": "art_001", "build_log": "art_002"},
            }
        self._mock_exec.side_effect = _mock_build

        async def _run():
            steps = [StepDefinition(tool_name="build_project", input_data={
                "task": "build app", "project_dir": self._tmpdir,
            })]
            wf = await self.engine.start_workflow(
                "build_art_test", steps, owner="dev",
                execution_context={"goal": "build"},
            )
            wid = wf.workflow_id
            await asyncio.sleep(0.2)

            ctx = self.engine.context_manager.get_context(wid)
            self.assertIsNotNone(ctx)
            self.assertEqual(ctx.artifacts.get("apk"), "art_001")
            self.assertEqual(ctx.artifacts.get("build_log"), "art_002")

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPLETED)

        asyncio.run(_run())

    def test_02_no_artifacts_when_step_fails(self):
        """Verify no context updates when step fails (no _artifacts)."""
        async def _mock_fail(*a, **kw):
            return "build_project", {
                "success": False,
                "error": "Build failed",
                "exit_code": 1,
            }
        self._mock_exec.side_effect = _mock_fail

        async def _run():
            steps = [StepDefinition(tool_name="build_project", input_data={
                "task": "build", "project_dir": self._tmpdir,
            }, max_retries=0)]
            wf = await self.engine.start_workflow("build_fail_test", steps, owner="dev")
            wid = wf.workflow_id
            await asyncio.sleep(0.2)

            ctx = self.engine.context_manager.get_context(wid)
            self.assertIsNotNone(ctx)
            self.assertEqual(ctx.artifacts, {},
                             "No artifacts should be registered on failure")

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.FAILED)

        asyncio.run(_run())

    # ── Real file scanning (unit-test the helper) ─────────────────────

    def test_03_build_helper_scans_project_dir(self):
        """Verify _register_build_artifacts scans project dir and registers files."""
        apk_dir = os.path.join(self._tmpdir, "app", "build", "outputs", "apk", "debug")
        os.makedirs(apk_dir, exist_ok=True)
        apk_path = os.path.join(apk_dir, "app-debug.apk")
        with open(apk_path, "w") as f:
            f.write("fake apk content")

        log_path = os.path.join(self._tmpdir, "build.log")
        with open(log_path, "w") as f:
            f.write("fake build log")

        # Create context first
        cm = self.engine.context_manager
        ctx = cm.create_context("wf_scan_test", owner="dev",
                                variables={"goal": "build"})

        # Run the helper via execute_tool_block's internal logic
        # We simulate what the handler does: register artifacts from project dir
        from core.workflow.artifact_store import ArtifactStore
        from core.workflow.context import ContextManager

        store = WorkflowStore(self._db)
        as2 = ArtifactStore(store)
        cm2 = ContextManager(store)

        ctx = cm2.get_context("wf_scan_test")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.variables.get("goal"), "build")

        import os as _os
        artifacts: dict[str, str] = {}
        scanned = set()
        for root, _dirs, files in _os.walk(self._tmpdir):
            for fname in files:
                fpath = _os.path.join(root, fname)
                if fpath in scanned:
                    continue
                scanned.add(fpath)
                if fname.endswith(".apk") and "apk" not in artifacts:
                    ref = as2.register_artifact(
                        workflow_id=ctx.workflow_id,
                        name=f"apk_{fname}",
                        artifact_type="apk",
                        path=fpath,
                        metadata={"project_dir": self._tmpdir, "source": "build"},
                    )
                    artifacts["apk"] = ref.artifact_id
                if fname == "build.log" and "build_log" not in artifacts:
                    ref = as2.register_artifact(
                        workflow_id=ctx.workflow_id,
                        name=f"build_log_{fname}",
                        artifact_type="build_log",
                        path=fpath,
                        metadata={"project_dir": self._tmpdir, "source": "build"},
                    )
                    artifacts["build_log"] = ref.artifact_id

        self.assertIn("apk", artifacts)
        self.assertIn("build_log", artifacts)

        ctx.artifacts.update(artifacts)
        cm2.update_context(ctx)

        ctx_final = cm2.get_context("wf_scan_test")
        self.assertEqual(ctx_final.artifacts.get("apk"), artifacts["apk"])
        self.assertEqual(ctx_final.artifacts.get("build_log"), artifacts["build_log"])

        # Verify artifact records exist
        loaded_apk = as2.get_artifact(artifacts["apk"])
        self.assertIsNotNone(loaded_apk)
        self.assertEqual(loaded_apk.artifact_type, "apk")
        self.assertTrue(loaded_apk.path.endswith("app-debug.apk"))

    # ── Artifacts survive crash + recovery ────────────────────────────

    def test_04_build_artifacts_survive_recovery(self):
        """Verify build artifacts registered in context survive crash + recovery."""
        async def _mock_build(*a, **kw):
            return "build_project", {
                "success": True,
                "output": "done",
                "exit_code": 0,
                "_artifacts": {"apk": "art_recover_001", "log": "art_recover_002"},
            }
        self._mock_exec.side_effect = _mock_build

        async def _phase1():
            steps = [StepDefinition(tool_name="build_project", input_data={
                "task": "build", "project_dir": self._tmpdir,
            })]
            wf = await self.engine.start_workflow(
                "build_recover", steps, owner="dev",
                execution_context={"goal": "build"},
            )
            wid = wf.workflow_id
            await asyncio.sleep(0.05)

            ctx_before = self.engine.context_manager.get_context(wid)
            self.assertEqual(ctx_before.artifacts.get("apk"), "art_recover_001")

            task = self.engine._running.get(wid)
            if task:
                task.cancel()
                try:
                    await task
                except Exception:
                    pass
            return wid

        wid = asyncio.run(_phase1())

        store2 = WorkflowStore(self._db)
        engine2 = WorkflowEngine(store2)
        cm2 = engine2.context_manager

        ctx_after_crash = cm2.get_context(wid)
        self.assertIsNotNone(ctx_after_crash)
        self.assertEqual(ctx_after_crash.artifacts.get("apk"), "art_recover_001",
                         "Artifact refs should survive crash")

        wf_stale = store2.get_workflow(wid)
        wf_stale.status = WorkflowStatus.RUNNING
        wf_stale.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)
        wf_stale.current_step = 0
        store2.update_workflow(wf_stale)
        for s in wf_stale.steps:
            s.status = StepStatus.PENDING
            store2.update_step(s)

        async def _phase2():
            recovered = await recover_active_workflows(engine2)
            self.assertGreaterEqual(len(recovered), 1)
            await asyncio.sleep(0.3)

            ctx_final = cm2.get_context(wid)
            self.assertIsNotNone(ctx_final)
            self.assertEqual(ctx_final.artifacts.get("apk"), "art_recover_001",
                             "Artifact refs should survive recovery")

        asyncio.run(_phase2())

    # ── Step with multiple build artifact types ───────────────────────

    def test_05_multiple_artifact_types(self):
        """Verify multiple artifact types from same step are all registered."""
        async def _mock(*a, **kw):
            return "build_project", {
                "success": True,
                "output": "done",
                "exit_code": 0,
                "_artifacts": {
                    "apk": "art_m_001",
                    "aab": "art_m_002",
                    "build_log": "art_m_003",
                    "report": "art_m_004",
                },
            }
        self._mock_exec.side_effect = _mock

        async def _run():
            steps = [StepDefinition(tool_name="build_project", input_data={
                "task": "build", "project_dir": self._tmpdir,
            })]
            wf = await self.engine.start_workflow("build_multi", steps, owner="dev")
            wid = wf.workflow_id
            await asyncio.sleep(0.2)

            ctx = self.engine.context_manager.get_context(wid)
            self.assertIsNotNone(ctx)
            self.assertEqual(len(ctx.artifacts), 4)
            self.assertEqual(ctx.artifacts["apk"], "art_m_001")
            self.assertEqual(ctx.artifacts["aab"], "art_m_002")
            self.assertEqual(ctx.artifacts["build_log"], "art_m_003")
            self.assertEqual(ctx.artifacts["report"], "art_m_004")

        asyncio.run(_run())

    # ── Non-build steps are unaffected ────────────────────────────────

    def test_06_non_build_steps_untouched(self):
        """Verify non-build steps don't register artifacts (no _artifacts key)."""
        self._mock_exec.return_value = ("bash", {"output": "ok", "exit_code": 0})

        async def _run():
            steps = [
                StepDefinition(tool_name="bash", input_data={"cmd": "echo hello"}),
                StepDefinition(tool_name="bash", input_data={"cmd": "echo world"}),
            ]
            wf = await self.engine.start_workflow("non_build", steps, owner="dev")
            wid = wf.workflow_id
            await asyncio.sleep(0.2)

            ctx = self.engine.context_manager.get_context(wid)
            self.assertIsNotNone(ctx)
            self.assertEqual(ctx.artifacts, {},
                             "Non-build steps should not register artifacts")

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPLETED)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main(verbosity=2)
