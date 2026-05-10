from __future__ import annotations

import json
import sqlite3
import threading
import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jarvis_os import JarvisOS as ExportedJarvisOS
from jarvis_os.agent import ExecutionEngine as ExportedExecutionEngine
from jarvis_os.cli.main import main as cli_main
from jarvis_os.bootstrap import build_jarvis_os
from jarvis_os.models.model_manager import ModelManager
from jarvis_os.models.ollama_router import OllamaRouter
from jarvis_os.models.rest_adapter import RestModelAdapter
from jarvis_os.runtime.config import JarvisConfig
from jarvis_os.runtime.logger import configure_logging, get_logger
from jarvis_os.utils import path_within_root, resolve_workspace_path
from jarvis_os.ProviderDecisionMatrix import ProviderDecisionMatrix
from jarvis_os.ProviderStrategicMemory import ProviderStrategicMemory
from jarvis_os.ProviderTrustRegistry import ProviderTrustRegistry
from jarvis_os.provider_health_registry import ProviderHealthRegistry
from jarvis_os.RuntimeGovernanceLayer import RuntimeGovernanceLayer


class JarvisOSTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        plugin_root = root / "plugins" / "demo_plugin"
        legacy_root = root / "legacy_backend"
        plugin_root.mkdir(parents=True, exist_ok=True)
        (legacy_root / "automation").mkdir(parents=True, exist_ok=True)
        (legacy_root / "data").mkdir(parents=True, exist_ok=True)
        (plugin_root / "manifest.json").write_text(
            json.dumps(
                {
                    "name": "demo_plugin",
                    "version": "1.0.0",
                    "description": "Demo plugin for tests.",
                    "tools": [
                        {
                            "name": "workspace_summary",
                            "description": "Summarize text through the core summarize tool.",
                            "category": "plugin",
                            "read_only": True,
                            "parameters": {"input": {"type": "string", "required": True}},
                            "keywords": ["plugin", "summary"],
                            "execution": {
                                "type": "proxy",
                                "tool": "summarize_text",
                                "arguments": {"text": "{{input}}"},
                            },
                        }
                    ],
                    "workflows": [
                        {
                            "name": "daily_digest",
                            "description": "Run a simple plugin workflow.",
                            "steps": [
                                {"tool": "summarize_text", "arguments": {"text": "{{input}}"}},
                                {"tool": "classify_text", "arguments": {"text": "{{input}}", "labels": ["digest", "other"]}},
                            ],
                        }
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (legacy_root / "automation" / "pc_automation.py").write_text(
            "def execute_command(text: str) -> dict:\n"
            "    return {'success': True, 'engine': 'legacy', 'command': text, 'summary': f'legacy:{text}'}\n",
            encoding="utf-8",
        )
        (legacy_root / "data" / "agi_memory.json").write_text(
            json.dumps(
                {
                    "events": [{"id": "evt_1", "mood": "focused", "text": "legacy event"}],
                    "goals": [{"id": "goal_1"}],
                    "decisions": [{"id": "decision_1"}],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (legacy_root / "data" / "contacts.json").write_text(
            json.dumps(
                {
                    "alice": {
                        "name": "Alice",
                        "phone": "12345",
                        "whatsapp": "12345",
                        "instagram": "alice.dev",
                        "email": "alice@example.com",
                        "notes": "legacy contact",
                        "added_at": "2026-01-01T00:00:00",
                    }
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        reminders_db = legacy_root / "data" / "jarvis.db"
        conn = sqlite3.connect(reminders_db)
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT UNIQUE,
                email TEXT UNIQUE,
                display_name TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                remind_at TEXT NOT NULL,
                repeat TEXT,
                is_done INTEGER DEFAULT 0,
                created_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO users (uid, email, display_name, created_at) VALUES (?, ?, ?, ?)",
            ("legacy-default", "legacy@example.com", "Legacy User", "2026-01-01 00:00:00"),
        )
        conn.execute(
            """
            INSERT INTO reminders (user_id, title, description, remind_at, repeat, is_done, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "Doctor appointment", "legacy reminder", "2099-01-01 09:00:00", "none", 0, "2026-01-01 00:00:00"),
        )
        conn.commit()
        conn.close()
        self.config = JarvisConfig(workspace_root=root, data_dir=root / "data", legacy_backend_root=str(legacy_root))
        self.runtime = build_jarvis_os(self.config)

    def tearDown(self) -> None:
        controller = getattr(self.runtime.tools, "browser_controller", None)
        if controller is not None and hasattr(controller, "close"):
            controller.close()
        self.runtime.wait_for_idle(timeout_s=3.0)
        self.runtime.daemon_stop()
        self.temp_dir.cleanup()

    def test_filesystem_prompt_executes(self) -> None:
        sample = self.config.workspace_root / "sample.txt"
        sample.write_text("hello", encoding="utf-8")
        result = self.runtime.handle_prompt("list directory .")
        self.assertEqual(result["intent"]["name"], "filesystem")
        self.assertTrue(result["execution"]["success"])
        self.assertEqual(result["plan"]["steps"][0]["tool"], "list_directory")

    def test_schedule_tool_persists(self) -> None:
        result = self.runtime.tools.invoke("schedule_task", name="heartbeat", command="echo hi", interval_s="60")
        self.assertTrue(result["scheduled"])
        self.assertEqual(result["interval_s"], 60)
        schedules = self.runtime.tools.invoke("list_schedules")
        self.assertEqual(len(schedules["items"]), 1)

    def test_general_prompt_falls_back_to_summary(self) -> None:
        result = self.runtime.handle_prompt("Summarize this short sentence.")
        self.assertTrue(result["execution"]["success"])
        self.assertEqual(result["plan"]["steps"][0]["tool"], "summarize_text")

    def test_preview_returns_collaboration_trace(self) -> None:
        preview = self.runtime.preview_prompt("list directory .")
        self.assertIn("collaborators", preview)
        self.assertGreaterEqual(len(preview["collaborators"]), 1)
        self.assertEqual(preview["plan"]["steps"][0]["tool"], "list_directory")
        self.assertIn("loop_trace", preview)
        self.assertEqual(preview["loop_trace"]["cycles"][0]["stages"][0]["name"], "observe")
        self.assertIn("agent_runtime", preview)

    def test_background_job_completes(self) -> None:
        submission = self.runtime.submit_prompt("list directory .")
        job_id = submission["job"]["job_id"]
        for _ in range(60):
            job = self.runtime.get_job(job_id)
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.1)
        self.assertEqual(job["status"], "completed")
        self.assertIn("result", job)

    def test_successful_run_promotes_skill_and_reuses_it(self) -> None:
        result = self.runtime.handle_prompt("list directory .")
        promoted_skill = result["self_improvement"]["promoted_skill"]
        self.assertTrue(promoted_skill)
        skills = self.runtime.list_skills()
        self.assertGreaterEqual(skills["count"], 1)
        preview = self.runtime.preview_prompt("list directory .")
        self.assertEqual(preview["plan"]["strategy"], "skill_reuse")
        self.assertIn("Matched learned skill", preview["plan"]["notes"][0])

    def test_run_skill_executes_learned_workflow(self) -> None:
        result = self.runtime.handle_prompt("list directory .")
        skill_name = result["self_improvement"]["promoted_skill"]
        skill_run = self.runtime.run_skill(skill_name)
        self.assertEqual(skill_run["skill"]["name"], skill_name)
        self.assertTrue(skill_run["execution"]["success"])

    def test_policy_blocks_delete_without_approval(self) -> None:
        target = self.config.workspace_root / "danger.txt"
        target.write_text("keep", encoding="utf-8")
        result = self.runtime.handle_prompt(f"delete file {target}")
        self.assertFalse(result["execution"]["success"])
        self.assertIn("requires explicit approval", result["execution"]["results"][0]["error"])
        self.assertEqual(result["loop_trace"]["cycles"][-1]["status"], "stopped")
        self.assertTrue(target.exists())

    def test_policy_allows_delete_with_tool_approval(self) -> None:
        target = self.config.workspace_root / "approved.txt"
        target.write_text("ok", encoding="utf-8")
        result = self.runtime.handle_prompt(
            f"delete file {target}",
            context={"approved_tools": ["delete_file"]},
        )
        self.assertTrue(result["execution"]["success"])
        self.assertFalse(target.exists())

    def test_policy_blocks_workspace_escape_for_file_write(self) -> None:
        outside = self.config.workspace_root.parent / "outside.txt"
        result = self.runtime.handle_prompt(
            "write file ../outside.txt hello",
            context={"approved_tools": ["write_file"]},
        )
        self.assertFalse(result["execution"]["success"])
        self.assertIn("workspace sandbox", result["execution"]["results"][0]["error"])
        self.assertFalse(outside.exists())

    def test_preview_reports_pending_approvals(self) -> None:
        target = self.config.workspace_root / "pending.txt"
        preview = self.runtime.preview_prompt(f"delete file {target}")
        self.assertEqual(preview["policy"]["pending_approvals"], 1)
        self.assertFalse(preview["policy"]["allowed"])

    def test_loop_trace_records_full_reasoning_cycle(self) -> None:
        result = self.runtime.handle_prompt("list directory .")
        cycle = result["loop_trace"]["cycles"][0]
        stage_names = [stage["name"] for stage in cycle["stages"]]
        self.assertEqual(stage_names, ["observe", "think", "plan", "act", "reflect"])
        self.assertEqual(result["loop_trace"]["status"], "completed")

    def test_failed_tool_result_triggers_recovery_cycle(self) -> None:
        result = self.runtime.handle_prompt("git status")
        self.assertTrue(result["execution"]["success"])
        self.assertGreaterEqual(len(result["loop_trace"]["cycles"]), 2)
        first_cycle = result["loop_trace"]["cycles"][0]
        self.assertEqual(first_cycle["stages"][3]["name"], "act")
        self.assertFalse(first_cycle["stages"][3]["data"]["success"])

    def test_tool_registry_validates_required_arguments(self) -> None:
        with self.assertRaises(ValueError):
            self.runtime.tools.invoke("write_file", content="hello")

    def test_tool_recommendation_prefers_news_tool_for_latest_news(self) -> None:
        recommended = self.runtime.tools.recommend("latest web3 news", "research")
        self.assertGreaterEqual(len(recommended), 1)
        self.assertEqual(recommended[0].name, "rss_news_fetch")

    def test_memory_persists_knowledge_between_runtime_instances(self) -> None:
        self.runtime.memory.remember_knowledge("Project codename is Sentinel.", {"topic": "project"})
        rebuilt = build_jarvis_os(self.config)
        hits = rebuilt.memory.search("Sentinel", kinds=["knowledge"])
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["kind"], "knowledge")

    def test_reasoning_observation_includes_knowledge_hits(self) -> None:
        self.runtime.memory.remember_knowledge("Web3 tracker should prioritize RSS feeds.", {"topic": "research"})
        preview = self.runtime.preview_prompt("latest web3 news")
        self.assertGreaterEqual(len(preview["observation"]["knowledge_hits"]), 1)
        self.assertIn("knowledge_hits", preview["analysis"])

    def test_handle_prompt_stores_conversation_turns(self) -> None:
        self.runtime.handle_prompt("hello jarvis")
        conversation = self.runtime.memory.conversation_recent(limit=4)
        speakers = [item["metadata"]["speaker"] for item in conversation[-2:]]
        self.assertEqual(speakers, ["user", "assistant"])

    def test_plugin_loader_discovers_manifest_and_registers_tool(self) -> None:
        plugins = self.runtime.list_plugins()
        self.assertEqual(plugins["count"], 1)
        plugin = plugins["plugins"][0]
        self.assertEqual(plugin["name"], "demo_plugin")
        tool_names = [item["name"] for item in self.runtime.tools.catalog()]
        self.assertIn("plugin.demo_plugin.workspace_summary", tool_names)

    def test_plugin_tool_executes_via_registry(self) -> None:
        result = self.runtime.tools.invoke("plugin.demo_plugin.workspace_summary", input="Plugin systems need summaries.")
        self.assertIn("summary", result)

    def test_plugin_workflow_runs(self) -> None:
        result = self.runtime.run_plugin_workflow("demo_plugin", "daily_digest", "Plugin workflow input")
        self.assertTrue(result["success"])
        self.assertEqual(result["steps"], 2)

    def test_agent_runtime_creates_isolated_workspace(self) -> None:
        agents = self.runtime.list_agents()
        self.assertGreaterEqual(agents["count"], 4)
        coding = self.runtime.get_agent("coding")
        self.assertTrue(Path(coding["workspace_root"]).exists())
        self.assertEqual(coding["memory_scope"], "coding")
        self.assertEqual(coding["model_task"], "coding")

    def test_agent_scoped_memory_isolation(self) -> None:
        self.runtime.memory.remember_knowledge("Coding agent prefers stack traces.", {"agent_scope": "coding"})
        self.runtime.memory.remember_knowledge("Research agent prefers RSS feeds.", {"agent_scope": "research"})
        coding_preview = self.runtime.preview_prompt("debug code", agent_name="coding")
        research_preview = self.runtime.preview_prompt("latest news", agent_name="research")
        coding_hits = " ".join(item["text"] for item in coding_preview["observation"]["knowledge_hits"])
        research_hits = " ".join(item["text"] for item in research_preview["observation"]["knowledge_hits"])
        self.assertIn("stack traces", coding_hits)
        self.assertNotIn("RSS feeds", coding_hits)
        self.assertIn("RSS feeds", research_hits)

    @unittest.skip("Requires live network LLM")
    def test_agent_queue_updates_for_background_jobs(self) -> None:
        submission = self.runtime.submit_prompt("list directory .", agent_name="coding")
        job_id = submission["job"]["job_id"]
        queued = self.runtime.get_agent("coding")
        self.assertGreaterEqual(queued["queue"]["queued"] + queued["queue"]["running"], 1)
        for _ in range(60):
            job = self.runtime.get_job(job_id)
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.1)
        agent_state = self.runtime.get_agent("coding")
        self.assertEqual(job["status"], "completed")
        self.assertGreaterEqual(agent_state["queue"]["completed"], 1)

    def test_scheduler_runs_due_tasks(self) -> None:
        self.runtime.tools.invoke("schedule_task", name="due_now", command="list directory .", interval_s=0)
        trigger = self.runtime.run_due_schedules()
        self.assertEqual(trigger["triggered"], 1)
        job_id = trigger["jobs"][0]["job_id"]
        for _ in range(60):
            job = self.runtime.get_job(job_id)
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.1)
        self.assertEqual(job["status"], "completed")

    def test_telemetry_records_execution(self) -> None:
        self.runtime.handle_prompt("list directory .")
        telemetry = self.runtime.telemetry_summary()
        self.assertGreaterEqual(telemetry["metrics"]["events"], 2)
        self.assertIn("tool.invoke", telemetry["metrics"]["by_type"])

    def test_config_summary_exposes_effective_runtime_settings(self) -> None:
        summary = self.runtime.config_summary()
        self.assertEqual(summary["workspace_root"], str(self.config.workspace_root))
        self.assertEqual(summary["data_dir"], str(self.config.data_dir))
        self.assertEqual(summary["log_level"], self.config.log_level)

    def test_monitor_summary_reports_runtime_snapshot(self) -> None:
        self.runtime.submit_prompt("list directory .", agent_name="coding")
        snapshot = self.runtime.monitor_summary()
        self.assertIn("job_counts", snapshot)
        self.assertIn("models", snapshot)
        self.assertIn("health", snapshot)
        self.assertGreaterEqual(snapshot["job_counts"].get("queued", 0) + snapshot["job_counts"].get("running", 0), 1)

    def test_browser_tools_expose_status_and_scrape_page(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                payload = b"<html><head><title>Browser Test</title></head><body>Local browser testing page.</body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args) -> None:  # noqa: A003
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            self.runtime.tools.browser_controller.playwright_available = False
            status = self.runtime.tools.invoke("browser_status")
            page = self.runtime.tools.invoke("scrape_page", url=f"http://127.0.0.1:{port}")
            self.assertTrue(status["success"])
            self.assertTrue(page["success"])
            self.assertEqual(page["title"], "Browser Test")
            self.assertIn("Local browser testing page.", page["text"])
        finally:
            server.shutdown()
            server.server_close()

    @unittest.skip("Requires live network LLM")
    def test_coding_prompt_routes_to_iterative_coding_loop(self) -> None:
        preview = self.runtime.preview_prompt("fix failing tests in .", agent_name="coding")
        self.assertEqual(preview["plan"]["steps"][0]["tool"], "coding_agent_loop")

    def test_coding_agent_loop_can_patch_workspace_and_rerun_tests(self) -> None:
        (self.config.workspace_root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        (self.config.workspace_root / "test_calc.py").write_text(
            "import unittest\n"
            "from calc import add\n\n"
            "class CalcTest(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(add(2, 3), 5)\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n",
            encoding="utf-8",
        )
        original_generate = self.runtime.models.generate

        def _fake_generate(prompt: str, task: str = "chat", system: str = "", *, options=None, model: str = "", provider: str = "") -> dict:
            return {
                "ok": True,
                "response": json.dumps(
                    {
                        "summary": "Fixed the arithmetic implementation.",
                        "files": [
                            {
                                "path": "calc.py",
                                "content": "def add(a, b):\n    return a + b\n",
                            }
                        ],
                    }
                ),
            }

        self.runtime.models.generate = _fake_generate
        try:
            result = self.runtime.tools.invoke("coding_agent_loop", prompt="fix failing tests in .", path=".", test_command="python -m unittest test_calc")
        finally:
            self.runtime.models.generate = original_generate
        self.assertTrue(result["success"])
        self.assertIn(str((self.config.workspace_root / "calc.py").resolve()), result["changed_files"])
        self.assertIn("Fixed the arithmetic implementation.", result["summary"])
        self.assertIn("return a + b", (self.config.workspace_root / "calc.py").read_text(encoding="utf-8"))

    @unittest.skip("Requires live network LLM")
    def test_background_job_can_pause_and_resume(self) -> None:
        original_handler = self.runtime.tools._handlers["list_directory"]

        def _slow_list_directory(**kwargs):
            time.sleep(0.15)
            return original_handler(**kwargs)

        self.runtime.tools._handlers["list_directory"] = _slow_list_directory
        try:
            submission = self.runtime.submit_prompt("list directory . and list directory .", agent_name="coding")
            job_id = submission["job"]["job_id"]
            for _ in range(40):
                job = self.runtime.get_job(job_id)
                if job["status"] == "running":
                    break
                time.sleep(0.05)
            self.runtime.pause_job(job_id)
            for _ in range(60):
                job = self.runtime.get_job(job_id)
                if job["status"] == "paused":
                    break
                time.sleep(0.05)
            self.assertEqual(job["status"], "paused")
            self.assertIn("checkpoint", job)
            self.runtime.resume_job(job_id)
            for _ in range(60):
                job = self.runtime.get_job(job_id)
                if job["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.1)
            self.assertEqual(job["status"], "completed")
            self.assertEqual(len(job["result"]["execution"]["results"]), 2)
        finally:
            self.runtime.tools._handlers["list_directory"] = original_handler

    @unittest.skip("Requires live network LLM")
    def test_paused_checkpoint_job_can_resume_after_runtime_rebuild(self) -> None:
        prompt = "list directory . and list directory ."
        preview = self.runtime.preview_prompt(prompt, agent_name="coding")
        first_step = preview["plan"]["steps"][0]
        job = self.runtime.jobs.create(prompt=prompt, agent_name="coding", context={}, plan=preview["plan"], preview=preview)
        self.runtime.jobs.update(
            job.job_id,
            status="paused",
            checkpoint={
                "plan_id": preview["plan"]["plan_id"],
                "next_step_index": 1,
                "active_step_id": "",
                "results": [
                    {
                        "tool": first_step["tool"],
                        "success": True,
                        "output": {"path": str(self.config.workspace_root), "exists": True, "entries": []},
                        "error": "",
                        "duration_ms": 1,
                        "step_id": first_step["step_id"],
                    }
                ],
            },
        )
        rebuilt = build_jarvis_os(self.config)
        rebuilt.resume_job(job.job_id)
        try:
            for _ in range(60):
                resumed = rebuilt.get_job(job.job_id)
                if resumed["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.1)
            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(len(resumed["result"]["execution"]["results"]), 2)
        finally:
            rebuilt.wait_for_idle(timeout_s=3.0)
            rebuilt.daemon_stop()

    def test_compat_summary_reports_legacy_adapters(self) -> None:
        compat = self.runtime.compat_summary()
        self.assertEqual(Path(compat["backend_root"]).resolve(), Path(self.config.legacy_backend_root).resolve())
        available = {item["name"]: item["available"] for item in compat["adapters"]}
        self.assertTrue(available["legacy_contacts"])
        self.assertTrue(available["legacy_agi_memory"])
        self.assertTrue(available["legacy_reminders"])
        self.assertTrue(available["legacy_pc_automation"])

    def test_legacy_agi_memory_tools_are_available(self) -> None:
        stats = self.runtime.tools.invoke("legacy_agi_memory_stats")
        recent = self.runtime.tools.invoke("legacy_agi_recent_events", limit=5)
        mood = self.runtime.tools.invoke("legacy_agi_latest_mood")
        self.assertEqual(stats["events"], 1)
        self.assertEqual(stats["goals"], 1)
        self.assertEqual(recent["events"][0]["id"], "evt_1")
        self.assertEqual(mood["mood"], "focused")

    def test_legacy_automation_tool_runs_through_compat_bridge(self) -> None:
        result = self.runtime.tools.invoke("legacy_automation_command", command="open chrome")
        self.assertTrue(result["success"])
        self.assertEqual(result["engine"], "legacy")
        self.assertEqual(result["command"], "open chrome")

    def test_legacy_contacts_tools_support_list_search_and_mutation(self) -> None:
        listed = self.runtime.tools.invoke("legacy_contacts_list")
        searched = self.runtime.tools.invoke("legacy_contacts_search", query="alice")
        saved = self.runtime.tools.invoke(
            "legacy_contacts_upsert",
            name="Bob",
            phone="55555",
            instagram="@bob.codes",
            email="bob@example.com",
            notes="new contact",
        )
        deleted = self.runtime.tools.invoke("legacy_contacts_delete", name="Bob")
        self.assertEqual(listed["count"], 1)
        self.assertEqual(searched["contacts"][0]["name"], "Alice")
        self.assertTrue(saved["saved"])
        self.assertEqual(saved["contact"]["instagram"], "bob.codes")
        self.assertTrue(deleted["deleted"])

    def test_legacy_reminders_tools_support_list_count_and_mutation(self) -> None:
        listed = self.runtime.tools.invoke("legacy_reminders_list", limit=10)
        pending = self.runtime.tools.invoke("legacy_reminders_pending_count")
        created = self.runtime.tools.invoke(
            "legacy_reminders_create",
            title="Call mom",
            remind_at="2099-01-02T10:30:00",
            description="legacy create",
        )
        deleted = self.runtime.tools.invoke("legacy_reminders_delete", reminder_id=created["reminder"]["id"])
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["reminders"][0]["title"], "Doctor appointment")
        self.assertEqual(pending["total"], 1)
        self.assertTrue(created["created"])
        self.assertEqual(created["reminder"]["title"], "Call mom")
        self.assertTrue(deleted["deleted"])

    def test_phase11_structure_exports_resolve(self) -> None:
        self.assertIsInstance(self.runtime, ExportedJarvisOS)
        self.assertTrue(callable(cli_main))
        self.assertEqual(ExportedExecutionEngine.__name__, "ExecutionEngine")

    def test_shared_path_utils_resolve_workspace_relative_paths(self) -> None:
        target = resolve_workspace_path("notes.txt", {"workspace_root": self.config.workspace_root})
        self.assertEqual(target, (self.config.workspace_root / "notes.txt").resolve())
        self.assertTrue(path_within_root(target, self.config.workspace_root))
        self.assertFalse(path_within_root(self.config.workspace_root.parent / "escape.txt", self.config.workspace_root))

    def test_daemon_tick_runs_due_schedule(self) -> None:
        self.runtime.tools.invoke("schedule_task", name="daemon_due", command="list directory .", interval_s=0)
        status = self.runtime.daemon_tick()
        self.assertGreaterEqual(status["ticks"], 1)
        self.assertEqual(status["last_result"]["triggered"], 1)

    def test_daemon_start_and_stop(self) -> None:
        started = self.runtime.daemon_start()
        self.assertTrue(started["running"])
        stopped = self.runtime.daemon_stop()
        self.assertFalse(stopped["running"])


class ModelLayerTest(unittest.TestCase):
    def test_model_manager_supports_rest_provider_and_streaming(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def _write(self, code: int, payload: dict) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._write(200, {"ready": True, "model": "rest-chat"})
                    return
                if self.path == "/models":
                    self._write(200, {"models": ["rest-chat", "rest-code"]})
                    return
                self._write(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                if self.path == "/generate":
                    if payload.get("stream"):
                        self.send_response(200)
                        self.send_header("Content-Type", "application/x-ndjson")
                        self.end_headers()
                        self.wfile.write(json.dumps({"response": "hello ", "done": False}).encode("utf-8") + b"\n")
                        self.wfile.write(json.dumps({"response": "world", "done": True}).encode("utf-8") + b"\n")
                        return
                    self._write(200, {"response": f"echo:{payload.get('prompt', '')}"})
                    return
                self._write(404, {"error": "not found"})

            def log_message(self, format: str, *args) -> None:  # noqa: A003
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            config = JarvisConfig(
                workspace_root=Path(tempfile.mkdtemp()),
                data_dir=Path(tempfile.mkdtemp()),
                model_provider="rest",
                model_api_base_url=f"http://127.0.0.1:{port}",
            )
            ollama = OllamaRouter(config)
            rest = RestModelAdapter(config)
            manager = ModelManager(rest, providers={"ollama": ollama, "rest": rest}, default_provider="rest")

            status = manager.status()
            self.assertEqual(status["active_provider"], "rest")
            self.assertTrue(status["providers"]["rest"]["ready"])

            generated = manager.generate("ping", provider="rest")
            self.assertTrue(generated["ok"])
            self.assertEqual(generated["response"], "echo:ping")

            streamed = manager.stream("ping", provider="rest")
            self.assertEqual("".join(item.get("chunk", "") for item in streamed if item.get("ok")), "hello world")
            self.assertTrue(streamed[-1]["done"])
        finally:
            server.shutdown()
            server.server_close()


class GovernanceSelectionTest(unittest.TestCase):
    def test_privacy_critical_task_prefers_offline_provider(self) -> None:
        config = JarvisConfig(
            workspace_root=Path(tempfile.mkdtemp()),
            data_dir=Path(tempfile.mkdtemp()),
            model_provider="rest",
        )
        providers = {"rest": None, "fallback": None, "ollama": None}
        trust_registry = ProviderTrustRegistry(providers)
        strategic_memory = ProviderStrategicMemory(config)
        decision_matrix = ProviderDecisionMatrix(config, trust_registry, strategic_memory)
        governance = RuntimeGovernanceLayer(trust_registry, ProviderHealthRegistry(providers), decision_matrix, strategic_memory, config)
        candidate_statuses = {
            "rest": {"ready": True, "provider": "rest", "models": ["rest-chat"], "base_url": "http://example.com"},
            "fallback": {"ready": True, "provider": "fallback", "models": ["offline-chat"]},
            "ollama": {"ready": True, "provider": "ollama", "models": ["llama3.1:8b"]},
        }
        selection = governance.finalize_selection(candidate_statuses, "private financial analysis", {})
        self.assertEqual(selection["provider"], "fallback")

    def test_deep_reasoning_task_prefers_reasoning_provider(self) -> None:
        config = JarvisConfig(
            workspace_root=Path(tempfile.mkdtemp()),
            data_dir=Path(tempfile.mkdtemp()),
            model_provider="ollama",
        )
        providers = {"rest": None, "fallback": None, "ollama": None}
        trust_registry = ProviderTrustRegistry(providers)
        strategic_memory = ProviderStrategicMemory(config)
        decision_matrix = ProviderDecisionMatrix(config, trust_registry, strategic_memory)
        governance = RuntimeGovernanceLayer(trust_registry, ProviderHealthRegistry(providers), decision_matrix, strategic_memory, config)
        candidate_statuses = {
            "rest": {"ready": True, "provider": "rest", "models": ["rest-chat"], "base_url": "http://example.com"},
            "fallback": {"ready": True, "provider": "fallback", "models": ["offline-chat"]},
            "ollama": {"ready": True, "provider": "ollama", "models": ["llama3.1:8b"]},
        }
        selection = governance.finalize_selection(candidate_statuses, "deep reasoning and planning", {})
        self.assertEqual(selection["provider"], "ollama")


class RuntimeLoggingTest(unittest.TestCase):
    def test_configure_logging_sets_named_logger_level(self) -> None:
        configure_logging("DEBUG")
        logger = get_logger("jarvis_os.tests")
        self.assertEqual(logger.getEffectiveLevel(), 10)


if __name__ == "__main__":
    unittest.main()
