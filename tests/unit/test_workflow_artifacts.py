"""ArtifactStore — Registration, Persistence, Recovery, Isolation Tests."""

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from core.workflow import (
    ArtifactRef,
    ArtifactStore,
    WorkflowEngine,
    WorkflowStore,
    recover_active_workflows,
)
from core.workflow.models import StepDefinition, StepStatus, WorkflowStatus


class WorkflowArtifactTests(unittest.TestCase):
    """Tests for ArtifactRef, ArtifactStore, and engine integration."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = os.path.join(self._tmpdir, "test_artifact.db")
        self.store = WorkflowStore(self._db)
        self.engine = WorkflowEngine(self.store)
        self.artifact_store = self.engine.artifact_store
        self._patcher = patch("core.tools.execution.execute_tool_block", new_callable=AsyncMock)
        self._mock_exec = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self.engine = None
        self.store = None

    # ── Artifact Lifecycle ─────────────────────────────────────────────

    def test_01_register_and_get_artifact(self):
        """Verify artifact registration and retrieval."""
        path = os.path.join(self._tmpdir, "test_file.txt")
        with open(path, "w") as f:
            f.write("hello world")

        ref = self.artifact_store.register_artifact(
            workflow_id="wf_art_01",
            name="test_file",
            artifact_type="text",
            path=path,
            metadata={"source": "test"},
        )
        self.assertEqual(ref.name, "test_file")
        self.assertEqual(ref.artifact_type, "text")
        self.assertIsNotNone(ref.artifact_id)
        self.assertGreater(ref.size_bytes, 0)
        self.assertIsNotNone(ref.checksum)

        loaded = self.artifact_store.get_artifact(ref.artifact_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "test_file")
        self.assertEqual(loaded.metadata["source"], "test")

    def test_02_list_artifacts(self):
        """Verify listing artifacts for a workflow."""
        for i in range(3):
            path = os.path.join(self._tmpdir, f"file_{i}.txt")
            with open(path, "w") as f:
                f.write(f"content {i}")
            self.artifact_store.register_artifact(
                workflow_id="wf_art_02",
                name=f"file_{i}",
                artifact_type="text",
                path=path,
            )

        artifacts = self.artifact_store.list_artifacts("wf_art_02")
        self.assertEqual(len(artifacts), 3)
        names = [a.name for a in artifacts]
        self.assertIn("file_0", names)
        self.assertIn("file_1", names)
        self.assertIn("file_2", names)

    def test_03_delete_artifact(self):
        """Verify artifact deletion from store."""
        path = os.path.join(self._tmpdir, "delete_me.txt")
        with open(path, "w") as f:
            f.write("delete me")
        ref = self.artifact_store.register_artifact(
            workflow_id="wf_art_03", name="to_delete", artifact_type="text", path=path,
        )
        self.assertIsNotNone(self.artifact_store.get_artifact(ref.artifact_id))
        self.artifact_store.delete_artifact(ref.artifact_id)
        self.assertIsNone(self.artifact_store.get_artifact(ref.artifact_id))

    # ── Artifact Persists Across Restart ───────────────────────────────

    def test_04_artifact_survives_store_reinit(self):
        """Verify artifact persists when store is re-initialized."""
        path = os.path.join(self._tmpdir, "persist.txt")
        with open(path, "w") as f:
            f.write("persist test")
        ref = self.artifact_store.register_artifact(
            workflow_id="wf_art_04", name="persist", artifact_type="text", path=path,
        )
        art_id = ref.artifact_id

        store2 = WorkflowStore(self._db)
        as2 = ArtifactStore(store2)
        loaded = as2.get_artifact(art_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "persist")
        self.assertEqual(loaded.path, path)

    # ── Artifact Survives Crash + Recovery ─────────────────────────────

    def test_05_artifact_survives_crash_recovery(self):
        """Verify artifact accessible after workflow crash + recovery."""
        self._mock_exec.return_value = ("bash", {"output": "ok", "exit_code": 0})

        path = os.path.join(self._tmpdir, "crash_survivor.txt")
        with open(path, "w") as f:
            f.write("crash survivor")

        async def _phase1():
            steps = [StepDefinition(tool_name="bash", input_data={"cmd": "build"})]
            wf = await self.engine.start_workflow("art_crash", steps, owner="dev")
            wid = wf.workflow_id

            ref = self.artifact_store.register_artifact(
                workflow_id=wid, name="output", artifact_type="build", path=path,
            )
            art_id = ref.artifact_id

            # Store artifact reference in context
            ctx = self.engine.context_manager.get_context(wid)
            ctx.artifacts["build_output"] = art_id
            self.engine.context_manager.update_context(ctx)

            await asyncio.sleep(0.05)
            task = self.engine._running.get(wid)
            if task:
                task.cancel()
                try:
                    await task
                except Exception:
                    pass
            return wid, art_id

        wid, art_id = asyncio.run(_phase1())

        store2 = WorkflowStore(self._db)
        engine2 = WorkflowEngine(store2)
        as2 = engine2.artifact_store
        cm2 = engine2.context_manager

        # Artifact should still exist
        loaded = as2.get_artifact(art_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "output")

        # Context should still have the reference
        ctx = cm2.get_context(wid)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.artifacts.get("build_output"), art_id)

        # Recover the workflow
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

            ctx_after = cm2.get_context(wid)
            self.assertIsNotNone(ctx_after)
            self.assertEqual(ctx_after.artifacts.get("build_output"), art_id,
                             "Artifact reference should survive recovery")
            loaded_after = as2.get_artifact(art_id)
            self.assertIsNotNone(loaded_after,
                                 "Artifact should survive crash recovery")

        asyncio.run(_phase2())

    # ── Workflow Artifact Isolation ────────────────────────────────────

    def test_06_artifact_isolation(self):
        """Verify artifacts are isolated between workflows."""
        path_a = os.path.join(self._tmpdir, "wf_a.txt")
        path_b = os.path.join(self._tmpdir, "wf_b.txt")
        with open(path_a, "w") as f:
            f.write("workflow A")
        with open(path_b, "w") as f:
            f.write("workflow B")

        ref_a = self.artifact_store.register_artifact(
            workflow_id="wf_a", name="report_a", artifact_type="text", path=path_a,
        )
        ref_b = self.artifact_store.register_artifact(
            workflow_id="wf_b", name="report_b", artifact_type="text", path=path_b,
        )

        arts_a = self.artifact_store.list_artifacts("wf_a")
        arts_b = self.artifact_store.list_artifacts("wf_b")
        self.assertEqual(len(arts_a), 1)
        self.assertEqual(len(arts_b), 1)
        self.assertEqual(arts_a[0].name, "report_a")
        self.assertEqual(arts_b[0].name, "report_b")
        self.assertNotEqual(arts_a[0].artifact_id, arts_b[0].artifact_id)

    # ── Checksum Computation ───────────────────────────────────────────

    def test_07_artifact_checksum(self):
        """Verify SHA-256 checksum is computed for file-based artifacts."""
        path = os.path.join(self._tmpdir, "checksum_test.txt")
        content = b"checksum this content"
        with open(path, "wb") as f:
            f.write(content)

        ref = self.artifact_store.register_artifact(
            workflow_id="wf_cs", name="checksum", artifact_type="text", path=path,
        )
        self.assertIsNotNone(ref.checksum)
        self.assertEqual(len(ref.checksum), 64)  # SHA-256 hex length

    # ── Context + Artifact End-to-End ──────────────────────────────────

    def test_08_context_artifacts_dict(self):
        """Verify context.artifacts dict is persisted and retrievable."""
        self.cm = self.engine.context_manager
        self.cm.create_context(
            "wf_e2e",
            artifacts={"apk": "art_001", "log": "art_002"},
        )

        ctx = self.cm.get_context("wf_e2e")
        self.assertEqual(ctx.artifacts["apk"], "art_001")
        self.assertEqual(ctx.artifacts["log"], "art_002")


    def test_09_no_file_artifact(self):
        """Verify artifact can be registered for non-existent path."""
        ref = self.artifact_store.register_artifact(
            workflow_id="wf_no_file",
            name="virtual",
            artifact_type="reference",
            path="/nonexistent/path.txt",
        )
        self.assertIsNotNone(ref.artifact_id)
        self.assertIsNone(ref.size_bytes)
        self.assertIsNone(ref.checksum)

        loaded = self.artifact_store.get_artifact(ref.artifact_id)
        self.assertIsNotNone(loaded)
        self.assertIsNone(loaded.size_bytes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
