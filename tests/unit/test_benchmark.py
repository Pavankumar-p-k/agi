"""Multi-Model Benchmark tests — Phase BM.1 through BM.3.

Covers:
  - Models: defaults, serialization, enums
  - Adapters: factory, mock adapter
  - Runner: raw mode, arch mode
  - Orchestrator: job matrix, aggregation
  - Results store: CRUD
  - Report generator: markdown, text, JSON
"""

import asyncio
import json
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from core.benchmark import (
    BenchmarkMode,
    BenchmarkReport,
    BenchmarkReportGenerator,
    BenchmarkResultsStore,
    BenchmarkRun,
    BenchmarkRunner,
    BenchmarkTask,
    BenchmarkTaskCategory,
    ModelConfiguration,
    ModelResult,
    RunStatus,
    create_adapter,
)
from core.benchmark.adapters import (
    AnthropicAdapter,
    OllamaAdapter,
    OpenAIAdapter,
)
from core.benchmark.orchestrator import (
    DEFAULT_MODELS,
    DEFAULT_TASKS,
    BenchmarkOrchestrator,
)


# ── Model Tests ──────────────────────────────────────────────────────


class TestModelConfiguration(unittest.TestCase):

    def test_01_defaults(self):
        cfg = ModelConfiguration("qwen2.5:7b", "Qwen 2.5 7B")
        self.assertEqual(cfg.provider, "ollama")
        self.assertEqual(cfg.endpoint, "http://localhost:11434")
        self.assertAlmostEqual(cfg.temperature, 0.0)

    def test_02_to_dict(self):
        cfg = ModelConfiguration("gpt-4o", "GPT-4o", "openai", "https://api.openai.com")
        d = cfg.to_dict()
        self.assertEqual(d["id"], "gpt-4o")
        self.assertEqual(d["provider"], "openai")

    def test_03_custom_temperature(self):
        cfg = ModelConfiguration("mistral:7b", "Mistral", temperature=0.7)
        self.assertAlmostEqual(cfg.temperature, 0.7)


class TestBenchmarkTask(unittest.TestCase):

    def test_10_defaults(self):
        t = BenchmarkTask("A", "Test Task", "Build something")
        self.assertEqual(t.category, BenchmarkTaskCategory.MULTI_STEP)
        self.assertEqual(t.required_tools, [])
        self.assertEqual(t.timeout_seconds, 300)

    def test_11_to_dict(self):
        t = BenchmarkTask("B", "APK", "Build APK", required_tools=["build_project"])
        d = t.to_dict()
        self.assertEqual(d["id"], "B")
        self.assertIn("build_project", d["required_tools"])


class TestBenchmarkRun(unittest.TestCase):

    def test_20_defaults(self):
        r = BenchmarkRun()
        self.assertTrue(r.run_id.startswith("run_"))
        self.assertEqual(r.status, RunStatus.SKIPPED)

    def test_21_is_success(self):
        self.assertTrue(BenchmarkRun(status=RunStatus.PASSED).is_success)
        self.assertFalse(BenchmarkRun(status=RunStatus.FAILED).is_success)

    def test_22_tool_accuracy_no_tools(self):
        r = BenchmarkRun()
        self.assertAlmostEqual(r.tool_accuracy, 0.0)

    def test_23_to_dict(self):
        now = datetime.now(timezone.utc).isoformat()
        r = BenchmarkRun(
            model_id="qwen", task_id="A", mode=BenchmarkMode.RAW,
            status=RunStatus.PASSED, elapsed_seconds=12.5,
            tool_names=["build_project"], hallucinated_tools=[],
        )
        d = r.to_dict()
        self.assertEqual(d["model_id"], "qwen")
        self.assertEqual(d["status"], "passed")
        self.assertAlmostEqual(d["elapsed_seconds"], 12.5)

    def test_24_generated_run_id(self):
        r1 = BenchmarkRun()
        r2 = BenchmarkRun()
        self.assertNotEqual(r1.run_id, r2.run_id)

    def test_25_provided_run_id(self):
        r = BenchmarkRun(run_id="custom_001")
        self.assertEqual(r.run_id, "custom_001")


class TestModelResult(unittest.TestCase):

    def test_30_empty_results(self):
        mr = ModelResult(ModelConfiguration("m", "M"))
        self.assertAlmostEqual(mr.raw_success_rate, 0.0)
        self.assertAlmostEqual(mr.arch_success_rate, 0.0)
        self.assertAlmostEqual(mr.average_gain, 0.0)

    def test_31_gain_computed(self):
        mr = ModelResult(ModelConfiguration("m", "M"))
        mr.raw_runs = [BenchmarkRun(status=RunStatus.FAILED),
                        BenchmarkRun(status=RunStatus.FAILED)]
        mr.arch_runs = [BenchmarkRun(status=RunStatus.PASSED),
                         BenchmarkRun(status=RunStatus.PASSED)]
        self.assertAlmostEqual(mr.raw_success_rate, 0.0)
        self.assertAlmostEqual(mr.arch_success_rate, 1.0)
        self.assertAlmostEqual(mr.average_gain, 1.0)

    def test_32_partial_gain(self):
        mr = ModelResult(ModelConfiguration("m", "M"))
        mr.raw_runs = [BenchmarkRun(status=RunStatus.PASSED),
                        BenchmarkRun(status=RunStatus.FAILED)]
        mr.arch_runs = [BenchmarkRun(status=RunStatus.PASSED),
                         BenchmarkRun(status=RunStatus.PASSED)]
        self.assertAlmostEqual(mr.raw_success_rate, 0.5)
        self.assertAlmostEqual(mr.arch_success_rate, 1.0)
        self.assertAlmostEqual(mr.average_gain, 0.5)

    def test_33_to_dict(self):
        mr = ModelResult(ModelConfiguration("qwen2.5:7b", "Qwen"))
        mr.raw_runs = [BenchmarkRun(status=RunStatus.PASSED)]
        mr.arch_runs = [BenchmarkRun(status=RunStatus.PASSED)]
        d = mr.to_dict()
        self.assertEqual(d["model_id"], "qwen2.5:7b")
        self.assertAlmostEqual(d["gain"], 0.0)


class TestBenchmarkReport(unittest.TestCase):

    def test_40_empty_report(self):
        r = BenchmarkReport()
        self.assertAlmostEqual(r.overall_avg_gain, 0.0)
        self.assertAlmostEqual(r.overall_avg_raw, 0.0)

    def test_41_overall_averages(self):
        mr1 = ModelResult(ModelConfiguration("m1", "M1"))
        mr1.raw_runs = [BenchmarkRun(status=RunStatus.FAILED)]
        mr1.arch_runs = [BenchmarkRun(status=RunStatus.PASSED)]

        mr2 = ModelResult(ModelConfiguration("m2", "M2"))
        mr2.raw_runs = [BenchmarkRun(status=RunStatus.PASSED)]
        mr2.arch_runs = [BenchmarkRun(status=RunStatus.FAILED)]

        r = BenchmarkReport(model_results=[mr1, mr2])
        self.assertAlmostEqual(r.overall_avg_raw, 0.5)
        self.assertAlmostEqual(r.overall_avg_arch, 0.5)
        self.assertAlmostEqual(r.overall_avg_gain, 0.0)

    def test_42_to_dict(self):
        report = BenchmarkReport(generated_at=datetime(2026, 6, 24, tzinfo=timezone.utc))
        d = report.to_dict()
        self.assertIsNotNone(d["generated_at"])
        self.assertEqual(d["tasks"], [])

    def test_43_markdown_table_basic(self):
        mr = ModelResult(ModelConfiguration("m", "Model"))
        mr.raw_runs = [BenchmarkRun(status=RunStatus.PASSED)]
        mr.arch_runs = [BenchmarkRun(status=RunStatus.PASSED)]
        report = BenchmarkReport(model_results=[mr])
        table = report.markdown_table()
        self.assertIn("Model", table)
        self.assertIn("+0%", table)


# ── Adapter Tests ────────────────────────────────────────────────────


class TestAdapterFactory(unittest.TestCase):

    def test_50_create_ollama(self):
        adapter = create_adapter("qwen2.5:7b", "ollama")
        self.assertIsInstance(adapter, OllamaAdapter)
        self.assertEqual(adapter.model_id, "qwen2.5:7b")

    def test_51_create_openai(self):
        adapter = create_adapter("gpt-4o", "openai", api_key="test-key")
        self.assertIsInstance(adapter, OpenAIAdapter)
        self.assertEqual(adapter.api_key, "test-key")

    def test_52_create_anthropic(self):
        adapter = create_adapter("claude-3-opus", "anthropic", api_key="test-key")
        self.assertIsInstance(adapter, AnthropicAdapter)

    def test_53_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            create_adapter("test", "unknown_provider")


# ── Runner Tests ─────────────────────────────────────────────────────


class TestBenchmarkRunner(unittest.TestCase):

    def setUp(self):
        self.adapter = MagicMock()
        self.adapter.model_id = "test-model"
        self.adapter.generate = AsyncMock(return_value=("I did it", []))
        self.runner = BenchmarkRunner(self.adapter)

    def test_60_raw_mode_returns_run(self):
        task = BenchmarkTask("T", "Test", "Do something")
        run = asyncio.run(self.runner.execute(task, mode=BenchmarkMode.RAW))
        self.assertIsNotNone(run)
        self.assertEqual(run.model_id, "test-model")
        self.assertEqual(run.task_id, "T")

    def test_61_arch_mode_returns_run(self):
        task = BenchmarkTask("T", "Test", "Do something")
        run = asyncio.run(self.runner.execute(task, mode=BenchmarkMode.WITH_ARCHITECTURE))
        self.assertIsNotNone(run)

    def test_62_timeout_handled(self):
        """asyncio.TimeoutError during generation should be caught as TIMEOUT."""
        async def slow(*args, **kwargs):
            raise asyncio.TimeoutError("timed out")

        self.adapter.generate = slow
        task = BenchmarkTask("T", "Test", "Do nothing", timeout_seconds=0.01)
        run = asyncio.run(self.runner.execute(task, mode=BenchmarkMode.RAW))
        self.assertEqual(run.status, RunStatus.TIMEOUT)

    def test_63_exception_handled(self):
        async def broken(*args, **kwargs):
            raise ValueError("test error")

        self.adapter.generate = broken
        task = BenchmarkTask("T", "Test", "Do something")
        run = asyncio.run(self.runner.execute(task, mode=BenchmarkMode.RAW))
        self.assertEqual(run.status, RunStatus.ERROR)
        self.assertIn("test error", run.error_message)


# ── Orchestrator Tests ───────────────────────────────────────────────


class TestBenchmarkOrchestrator(unittest.TestCase):

    def setUp(self):
        self.orchestrator = BenchmarkOrchestrator(concurrency=1)

    def test_70_default_models_and_tasks(self):
        self.assertGreater(len(DEFAULT_MODELS), 0)
        self.assertGreater(len(DEFAULT_TASKS), 0)

    def test_71_default_models_have_ollama_provider(self):
        for m in DEFAULT_MODELS:
            self.assertEqual(m.provider, "ollama")

    def test_72_empty_modes_raises(self):
        with self.assertRaises(ValueError):
            asyncio.run(self.orchestrator.run_all(include_raw=False, include_arch=False))

    def test_73_orchestrator_can_instantiate(self):
        o = BenchmarkOrchestrator(concurrency=3, verbose=True)
        self.assertEqual(o.concurrency, 3)
        self.assertTrue(o.verbose)


# ── Results Store Tests ──────────────────────────────────────────────


class TestBenchmarkResultsStore(unittest.TestCase):

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.store = BenchmarkResultsStore(self.tmp_db.name)

    def tearDown(self):
        import os
        try:
            os.unlink(self.tmp_db.name)
        except OSError:
            pass

    def test_80_save_and_get_run(self):
        run = BenchmarkRun(
            model_id="test", task_id="A", mode=BenchmarkMode.RAW,
            status=RunStatus.PASSED, elapsed_seconds=10.0,
            tool_names=["build_project"],
        )
        self.store.save_run(run)
        loaded = self.store.get_run(run.run_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.model_id, "test")
        self.assertEqual(loaded.status, RunStatus.PASSED)

    def test_81_list_runs_empty(self):
        runs = self.store.list_runs()
        self.assertEqual(runs, [])

    def test_82_list_runs_filtered(self):
        r1 = BenchmarkRun(model_id="m1", task_id="A", mode=BenchmarkMode.RAW,
                           status=RunStatus.PASSED)
        r2 = BenchmarkRun(model_id="m2", task_id="B", mode=BenchmarkMode.RAW,
                           status=RunStatus.FAILED)
        self.store.save_run(r1)
        self.store.save_run(r2)
        runs = self.store.list_runs(model_id="m1")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].model_id, "m1")

    def test_83_save_task(self):
        task = BenchmarkTask("X", "Extra", "Do extra stuff")
        self.store.save_task(task)

    def test_84_save_and_list_reports(self):
        report = BenchmarkReport(generated_at=datetime.now(timezone.utc))
        rid = self.store.save_report(report, "test-session")
        self.assertGreater(rid, 0)
        reports = self.store.list_reports()
        self.assertGreater(len(reports), 0)

    def test_85_get_report(self):
        report = BenchmarkReport(generated_at=datetime.now(timezone.utc))
        rid = self.store.save_report(report)
        loaded = self.store.get_report(rid)
        self.assertIsNotNone(loaded)
        self.assertIn("generated_at", loaded)

    def test_86_overall_stats(self):
        r = BenchmarkRun(model_id="m", task_id="A", mode=BenchmarkMode.RAW,
                          status=RunStatus.PASSED)
        self.store.save_run(r)
        stats = self.store.get_overall_stats()
        self.assertGreater(stats["total_runs"], 0)

    def test_87_get_nonexistent_run(self):
        run = self.store.get_run("nonexistent")
        self.assertIsNone(run)

    def test_88_get_nonexistent_report(self):
        report = self.store.get_report(99999)
        self.assertIsNone(report)


# ── Report Generator Tests ───────────────────────────────────────────


class TestBenchmarkReportGenerator(unittest.TestCase):

    def setUp(self):
        self.generator = BenchmarkReportGenerator()

    def test_90_markdown_includes_sections(self):
        mr = ModelResult(ModelConfiguration("m", "Model"))
        mr.raw_runs = [BenchmarkRun(status=RunStatus.PASSED, elapsed_seconds=5.0)]
        mr.arch_runs = [BenchmarkRun(status=RunStatus.PASSED, elapsed_seconds=8.0)]
        report = BenchmarkReport(
            model_results=[mr],
            tasks=[BenchmarkTask("T", "Test", "Goal")],
            generated_at=datetime.now(timezone.utc),
        )
        md = self.generator.to_markdown(report)
        self.assertIn("Summary", md)
        self.assertIn("Model", md)
        self.assertIn("Per-Model Detail", md)
        self.assertIn("Task Definitions", md)

    def test_91_json_output(self):
        mr = ModelResult(ModelConfiguration("m", "M"))
        report = BenchmarkReport(model_results=[mr])
        js = self.generator.to_json(report)
        data = json.loads(js)
        self.assertIn("models", data)

    def test_92_text_summary(self):
        mr = ModelResult(ModelConfiguration("m", "Model A"))
        mr.raw_runs = [BenchmarkRun(status=RunStatus.PASSED)]
        mr.arch_runs = [BenchmarkRun(status=RunStatus.PASSED)]
        report = BenchmarkReport(model_results=[mr])
        txt = self.generator.to_text_summary(report)
        self.assertIn("Model A", txt)
        self.assertIn("Gain", txt)
        self.assertIn("Average", txt)

    def test_93_empty_report_markdown(self):
        report = BenchmarkReport()
        md = self.generator.to_markdown(report)
        self.assertIn("Summary", md)

    def test_94_markdown_shows_different_modes(self):
        mr = ModelResult(ModelConfiguration("m", "M1"))
        mr.raw_runs = [BenchmarkRun(status=RunStatus.PASSED, task_id="A"),
                        BenchmarkRun(status=RunStatus.FAILED, task_id="B")]
        mr.arch_runs = [BenchmarkRun(status=RunStatus.PASSED, task_id="A"),
                         BenchmarkRun(status=RunStatus.PASSED, task_id="B")]
        report = BenchmarkReport(model_results=[mr], generated_at=datetime.now(timezone.utc))
        md = self.generator.to_markdown(report)
        # Should show two tables — one for raw, one for arch
        self.assertIn("Task | Status | Time | Turns", md)
        self.assertIn("Task | Status | Time | Tools | Hallucinated | Missing", md)


if __name__ == "__main__":
    unittest.main()
