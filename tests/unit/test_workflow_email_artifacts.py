"""Email Artifact Integration — artifact: refs resolved in attachments, sent email registered as artifact."""

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.workflow import (
    WorkflowEngine,
    WorkflowStore,
)
from core.workflow.models import StepDefinition, WorkflowStatus
from core.tools.execution import _register_email_artifact, _resolve_artifact_attachments


class WorkflowEmailArtifactTests(unittest.TestCase):
    """Tests for email artifact resolution and registration."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = os.path.join(self._tmpdir, "test_email_artifact.db")
        self.store = WorkflowStore(self._db)
        self.engine = WorkflowEngine(self.store)
        self.art_store = self.engine.artifact_store
        self.cm = self.engine.context_manager

    def tearDown(self):
        self.engine = None
        self.store = None

    # ── _resolve_artifact_attachments ────────────────────────────────

    def test_01_resolves_valid_artifact_ref(self):
        """Verify artifact: ref is resolved to file path."""
        ctx = self.cm.create_context("wf_email_01", owner="dev",
                                     metadata={"_store_path": self._db})
        test_file = os.path.join(self._tmpdir, "report.pdf")
        with open(test_file, "w") as f:
            f.write("fake report")
        ref = self.art_store.register_artifact(
            workflow_id="wf_email_01", name="report",
            artifact_type="report", path=test_file,
        )
        attachments = [f"artifact:{ref.artifact_id}"]
        resolved = _resolve_artifact_attachments(attachments, ctx)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0], test_file)

    def test_02_invalid_artifact_ref_unchanged(self):
        """Verify invalid artifact: ref is returned unchanged."""
        ctx = self.cm.create_context("wf_email_02", owner="dev",
                                     metadata={"_store_path": self._db})
        attachments = ["artifact:nonexistent_id"]
        resolved = _resolve_artifact_attachments(attachments, ctx)
        self.assertEqual(resolved, attachments)

    def test_03_no_artifact_refs_unchanged(self):
        """Verify plain paths are returned unchanged."""
        ctx = self.cm.create_context("wf_email_03", owner="dev",
                                     metadata={"_store_path": self._db})
        attachments = ["/path/to/file.pdf", "/path/to/image.png"]
        resolved = _resolve_artifact_attachments(attachments, ctx)
        self.assertEqual(resolved, attachments)

    def test_04_mixed_refs_and_paths(self):
        """Verify mixed artifact refs and file paths resolve correctly."""
        ctx = self.cm.create_context("wf_email_04", owner="dev",
                                     metadata={"_store_path": self._db})
        test_png = os.path.join(self._tmpdir, "screenshot.png")
        with open(test_png, "w") as f:
            f.write("fake png")
        ref = self.art_store.register_artifact(
            workflow_id="wf_email_04", name="ss",
            artifact_type="screenshot", path=test_png,
        )
        attachments = ["/path/existing.pdf", f"artifact:{ref.artifact_id}"]
        resolved = _resolve_artifact_attachments(attachments, ctx)
        self.assertEqual(len(resolved), 2)
        self.assertEqual(resolved[0], "/path/existing.pdf")
        self.assertEqual(resolved[1], test_png)

    def test_05_no_context_returns_attachments_unchanged(self):
        """Verify attachments unchanged when context is None."""
        attachments = ["artifact:art_001", "/path/file.pdf"]
        resolved = _resolve_artifact_attachments(attachments, None)
        self.assertEqual(resolved, attachments)

    # ── _register_email_artifact ─────────────────────────────────────

    def test_06_registers_email_artifact(self):
        """Verify sent email is registered as email_sent artifact."""
        ctx = self.cm.create_context("wf_email_06", owner="dev",
                                     metadata={"_store_path": self._db})
        result = {
            "sent": True,
            "to": ["user@example.com"],
            "subject": "Hello",
            "message_id": "<abc123@example.com>",
        }
        artifacts = asyncio.run(_register_email_artifact(result, ctx))
        self.assertIn("email_sent", artifacts)
        art_id = artifacts["email_sent"]
        art = self.art_store.get_artifact(art_id)
        self.assertIsNotNone(art)
        self.assertEqual(art.artifact_type, "email_sent")
        self.assertEqual(art.metadata.get("to"), ["user@example.com"])
        self.assertEqual(art.metadata.get("subject"), "Hello")
        self.assertIn("sent_at", art.metadata)

        ctx_loaded = self.cm.get_context("wf_email_06")
        self.assertIn("email_sent", ctx_loaded.artifacts)

    def test_07_no_context_returns_empty(self):
        """Verify no artifact when context is None."""
        result = {"sent": True, "to": ["u@e.com"], "subject": "test",
                  "message_id": "<m@e.com>"}
        artifacts = asyncio.run(_register_email_artifact(result, None))
        self.assertEqual(artifacts, {})

    # ── Engine integration: end-to-end via mocked MCP ────────────────

    def test_08_engine_resolves_artifacts_and_registers_email(self):
        """Verify engine resolves artifact refs and registers email artifact via MCP."""
        test_file = os.path.join(self._tmpdir, "build_report.html")
        with open(test_file, "w") as f:
            f.write("<html>build report</html>")

        captured_args = [None]

        async def _mock_mcp_call(tool, args):
            captured_args[0] = args
            return {
                "sent": True,
                "to": ["dev@example.com"],
                "subject": "Build Report",
                "message_id": "<build@jarvis>",
            }

        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(side_effect=_mock_mcp_call)

        async def _run():
            reg_ref = self.art_store.register_artifact(
                workflow_id="wf_e2e_08", name="report",
                artifact_type="report", path=test_file,
            )
            steps = [
                StepDefinition(
                    tool_name="mcp__email__send_email",
                    input_data={
                        "to": "dev@example.com",
                        "subject": "Build Report",
                        "body": "Your build is ready.",
                        "attachments": [
                            f"artifact:{reg_ref.artifact_id}",
                            "/path/extra.log",
                        ],
                    },
                ),
            ]
            with patch("core.tools.execution.get_mcp_manager", return_value=mock_mcp):
                wf = await self.engine.start_workflow(
                    "wf_e2e_08", steps, owner="dev",
                    execution_context={"task": "email build"},
                )
                wid = wf.workflow_id
                await asyncio.sleep(0.4)

            ctx = self.cm.get_context(wid)
            self.assertIsNotNone(ctx)
            self.assertIn("email_sent", ctx.artifacts,
                          "Sent email should be registered as artifact")

            art_id = ctx.artifacts["email_sent"]
            art = self.art_store.get_artifact(art_id)
            self.assertIsNotNone(art)
            self.assertEqual(art.artifact_type, "email_sent")
            self.assertEqual(art.metadata.get("subject"), "Build Report")

            # Verify artifact ref was resolved before MCP call
            called_args = captured_args[0]
            self.assertIsNotNone(called_args)
            attachments = called_args.get("attachments", [])
            self.assertEqual(len(attachments), 2)
            self.assertEqual(attachments[0], test_file,
                             "Artifact ref should be resolved to file path")
            self.assertEqual(attachments[1], "/path/extra.log")

            final = self.store.get_workflow(wid)
            self.assertEqual(final.status, WorkflowStatus.COMPLETED)

        asyncio.run(_run())

    def test_09_engine_no_artifact_when_email_fails(self):
        """Verify no email artifact when send fails."""
        async def _mock_fail(tool, args):
            return {"sent": False, "error": "SMTP unavailable"}

        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(side_effect=_mock_fail)

        async def _run():
            steps = [
                StepDefinition(
                    tool_name="mcp__email__send_email",
                    input_data={"to": "x@y.com", "subject": "Fail", "body": "oops"},
                ),
            ]
            with patch("core.tools.execution.get_mcp_manager", return_value=mock_mcp):
                wf = await self.engine.start_workflow(
                    "wf_email_09", steps, owner="dev",
                    execution_context={"task": "fail email"},
                )
                wid = wf.workflow_id
                await asyncio.sleep(0.3)

            ctx = self.cm.get_context(wid)
            self.assertIsNotNone(ctx)
            self.assertNotIn("email_sent", ctx.artifacts or {},
                             "No email artifact on failure")

        asyncio.run(_run())

    # ── _attach_files_to_msg (unit test via email_server import) ──────

    def test_10_attach_files_to_msg(self):
        """Verify attach_files_to_msg reads files and attaches to EmailMessage."""
        from email.message import EmailMessage
        from core.tools.email_utils import attach_files_to_msg

        test_txt = os.path.join(self._tmpdir, "hello.txt")
        with open(test_txt, "w") as f:
            f.write("Hello World")
        test_png = os.path.join(self._tmpdir, "img.png")
        with open(test_png, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")

        msg = EmailMessage()
        msg.set_content("body")
        attach_files_to_msg(msg, [test_txt, test_png])

        parts = list(msg.walk())
        attached = [p for p in parts if p.get_filename()]
        self.assertEqual(len(attached), 2)
        names = {p.get_filename() for p in attached}
        self.assertIn("hello.txt", names)
        self.assertIn("img.png", names)

        txt_part = [p for p in attached if p.get_filename() == "hello.txt"][0]
        self.assertEqual(txt_part.get_payload(decode=True).decode(), "Hello World")

    def test_11_attach_files_nonexistent_skipped(self):
        """Verify nonexistent files are skipped without error."""
        from email.message import EmailMessage
        from core.tools.email_utils import attach_files_to_msg

        msg = EmailMessage()
        msg.set_content("body")
        attach_files_to_msg(msg, ["/nonexistent/file.pdf"])
        parts = list(msg.walk())
        attached = [p for p in parts if p.get_filename()]
        self.assertEqual(len(attached), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
