"""Browser Artifact Integration — screenshots, snapshots registered as artifacts."""

import asyncio
import base64
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from core.workflow import (
    WorkflowEngine,
    WorkflowStore,
    recover_active_workflows,
)
from core.workflow.models import StepDefinition, WorkflowStatus


class WorkflowBrowserArtifactTests(unittest.TestCase):
    """Tests for browser artifact registration through the workflow engine."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = os.path.join(self._tmpdir, "test_browser_artifact.db")
        self.store = WorkflowStore(self._db)
        self.engine = WorkflowEngine(self.store)
        self.art_store = self.engine.artifact_store
        self.cm = self.engine.context_manager

    def tearDown(self):
        self.engine = None
        self.store = None

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _fake_png_b64() -> str:
        """Return a valid 1x1 red PNG as base64."""
        return base64.b64encode(
            bytes.fromhex(
                "89504e470d0a1a0a"  # PNG header
                "0000000d49484452"  # IHDR chunk
                "0000000100000001"  # 1x1
                "0802000000907753"  # 8-bit grayscale
                "de0000000c494441"  # IDAT chunk
                "5408d76360f8cf"    # (compressed data)
                "5000000000ffff"    #
                "ffffffff3a00dfc0"  #
                "01000000c0494e44"  # IEND
                "ae426082"          #
            )
        ).decode("utf-8")

    # ── browser_screenshot saves PNG and registers artifact ──────────

    def test_01_browser_screenshot_registers_artifact(self):
        """Verify browser_screenshot saves PNG and registers screenshot artifact."""
        fake_b64 = self._fake_png_b64()

        async def _mock_screenshot(*a, **kw):
            return {"screenshot": fake_b64, "mime": "image/png",
                    "url": "https://example.com", "title": "Test Page"}

        async def _run():
            with patch("core.tools.implementations.do_browser_screenshot",
                       side_effect=_mock_screenshot):
                steps = [StepDefinition(tool_name="browser_screenshot", input_data={})]
                wf = await self.engine.start_workflow(
                    "browser_ss_test", steps, owner="dev",
                    execution_context={"task": "take screenshot"},
                )
                wid = wf.workflow_id
                await asyncio.sleep(0.3)

            ctx = self.cm.get_context(wid)
            self.assertIsNotNone(ctx)
            self.assertIn("screenshot", ctx.artifacts,
                          "Screenshot artifact should be registered")

            art_id = ctx.artifacts["screenshot"]
            art = self.art_store.get_artifact(art_id)
            self.assertIsNotNone(art, "Artifact record should exist")
            self.assertEqual(art.artifact_type, "screenshot")
            self.assertTrue(art.path.endswith(".png"),
                            f"Artifact path should be a PNG: {art.path}")
            self.assertGreater(art.size_bytes, 0,
                               "Saved PNG should have content")
            self.assertEqual(art.metadata.get("url"), "https://example.com")

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPLETED)

        asyncio.run(_run())

    # ── browser_snapshot saves JSON and registers artifact ───────────

    def test_02_browser_snapshot_registers_artifact(self):
        """Verify browser_snapshot saves JSON and registers html_snapshot artifact."""
        fake_snapshot = {
            "url": "https://example.com",
            "title": "Example",
            "buttons": [{"tag": "button", "text": "Submit", "visible": True}],
            "inputs": [{"tag": "input", "name": "q", "visible": True}],
            "links": [{"tag": "a", "text": "About", "href": "/about", "visible": True}],
            "headings": [],
            "forms": [],
            "shadow_elements": [],
            "contenteditable": [],
            "modals": [],
            "dialogs": [],
        }

        async def _mock_snapshot(*a, **kw):
            return dict(fake_snapshot)

        async def _run():
            with patch("core.tools.implementations.do_browser_snapshot",
                       side_effect=_mock_snapshot):
                steps = [StepDefinition(tool_name="browser_snapshot", input_data={})]
                wf = await self.engine.start_workflow(
                    "browser_snap_test", steps, owner="dev",
                    execution_context={"task": "snapshot page"},
                )
                wid = wf.workflow_id
                await asyncio.sleep(0.3)

            ctx = self.cm.get_context(wid)
            self.assertIsNotNone(ctx)
            self.assertIn("snapshot", ctx.artifacts,
                          "Snapshot artifact should be registered")

            art_id = ctx.artifacts["snapshot"]
            art = self.art_store.get_artifact(art_id)
            self.assertIsNotNone(art, "Artifact record should exist")
            self.assertEqual(art.artifact_type, "html_snapshot")
            self.assertTrue(art.path.endswith(".json"),
                            f"Artifact path should be JSON: {art.path}")
            self.assertGreater(art.size_bytes, 0)

            # Verify saved JSON content
            with open(art.path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(len(saved["buttons"]), 1)
            self.assertEqual(saved["buttons"][0]["text"], "Submit")
            self.assertEqual(len(saved["inputs"]), 1)
            self.assertEqual(saved["inputs"][0]["name"], "q")

        asyncio.run(_run())

    # ── No artifacts when result has error ───────────────────────────

    def test_03_no_artifacts_on_error(self):
        """Verify no artifacts when browser tool returns an error."""
        async def _mock_error(*a, **kw):
            return {"error": "Browser not connected", "error_type": "BrowserError"}

        async def _run():
            with patch("core.tools.implementations.do_browser_screenshot",
                       side_effect=_mock_error):
                steps = [StepDefinition(tool_name="browser_screenshot", input_data={})]
                wf = await self.engine.start_workflow(
                    "browser_err_test", steps, owner="dev",
                    execution_context={"task": "fail"},
                )
                wid = wf.workflow_id
                await asyncio.sleep(0.3)

            ctx = self.cm.get_context(wid)
            self.assertIsNotNone(ctx)
            self.assertEqual(ctx.artifacts, {},
                             "No artifacts should be registered on error")

        asyncio.run(_run())

    # ── Artifacts survive crash + recovery ───────────────────────────

    def test_04_browser_artifacts_survive_recovery(self):
        """Verify browser artifacts survive crash + recovery cycle."""
        from datetime import datetime, timedelta
        from core.workflow.models import StepStatus

        fake_b64 = self._fake_png_b64()

        async def _mock(*a, **kw):
            return {"screenshot": fake_b64, "mime": "image/png",
                    "url": "https://example.com", "title": "Test"}

        async def _phase1():
            with patch("core.tools.implementations.do_browser_screenshot",
                       side_effect=_mock):
                steps = [StepDefinition(tool_name="browser_screenshot", input_data={})]
                wf = await self.engine.start_workflow(
                    "browser_recover", steps, owner="dev",
                    execution_context={"task": "screenshot"},
                )
                wid = wf.workflow_id
                await asyncio.sleep(0.1)

                ctx_before = self.cm.get_context(wid)
                self.assertIn("screenshot", ctx_before.artifacts)

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
        as2 = engine2.artifact_store  # noqa: N806

        # Verify artifacts survive store reinit
        ctx_survive = cm2.get_context(wid)
        self.assertIsNotNone(ctx_survive)
        art_id = ctx_survive.artifacts.get("screenshot")
        self.assertIsNotNone(art_id,
                             "Screenshot artifact should survive store reinit")
        art = as2.get_artifact(art_id)
        self.assertIsNotNone(art)
        self.assertEqual(art.artifact_type, "screenshot")

        # Mark as stale and recover
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

            ctx_final = cm2.get_context(wid)
            self.assertIsNotNone(ctx_final)
            self.assertIn("screenshot", ctx_final.artifacts,
                          "Artifacts should survive recovery")

        asyncio.run(_phase2())

    # ── Screenshot + snapshot in same workflow ───────────────────────

    def test_05_multiple_browser_artifacts(self):
        """Verify screenshot + snapshot from different steps register separately."""
        fake_b64 = self._fake_png_b64()

        async def _run():
            with (
                patch("core.tools.implementations.do_browser_screenshot",
                      return_value={
                          "screenshot": fake_b64, "mime": "image/png",
                          "url": "https://a.com", "title": "Page A",
                      }),
                patch("core.tools.implementations.do_browser_snapshot",
                      return_value={
                          "url": "https://b.com", "title": "Page B",
                          "buttons": [], "inputs": [], "links": [],
                          "headings": [], "forms": [], "shadow_elements": [],
                          "contenteditable": [], "modals": [], "dialogs": [],
                      }),
            ):
                steps = [
                    StepDefinition(tool_name="browser_screenshot", input_data={}),
                    StepDefinition(tool_name="browser_snapshot", input_data={}),
                ]
                wf = await self.engine.start_workflow(
                    "browser_multi", steps, owner="dev",
                    execution_context={"task": "multi"},
                )
                wid = wf.workflow_id
                await asyncio.sleep(0.4)

            ctx = self.cm.get_context(wid)
            self.assertIsNotNone(ctx)
            self.assertIn("screenshot", ctx.artifacts)
            self.assertIn("snapshot", ctx.artifacts)
            self.assertNotEqual(ctx.artifacts["screenshot"],
                                ctx.artifacts["snapshot"],
                                "Distinct artifacts should have different IDs")

            ss_art = self.art_store.get_artifact(ctx.artifacts["screenshot"])
            snap_art = self.art_store.get_artifact(ctx.artifacts["snapshot"])
            self.assertIsNotNone(ss_art)
            self.assertIsNotNone(snap_art)
            self.assertEqual(ss_art.artifact_type, "screenshot")
            self.assertEqual(snap_art.artifact_type, "html_snapshot")

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main(verbosity=2)
