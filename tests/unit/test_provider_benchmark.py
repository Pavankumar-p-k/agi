"""Tests for the Provider Benchmark Suite (X.2)."""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from core.providers.benchmark import (
    BenchmarkTask, BenchmarkResult, BenchmarkRunner, BenchmarkCategory,
    get_tasks, get_categories, score_quality, TASKS,
)
from core.providers.benchmark_store import BenchmarkStore, BenchmarkSummary


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_db():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "benchmark_test.db")
    yield db_path
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def store(temp_db):
    return BenchmarkStore(db_path=temp_db)


@pytest.fixture
def sample_result():
    return BenchmarkResult(
        task_id="py_crud_api",
        provider_id="forge",
        category="python",
        language="python",
        framework="fastapi",
        success=True,
        duration_ms=15000.0,
        quality_score=0.85,
        retries=0,
        crash=False,
        cost=0.0,
        tokens_used=500,
        exit_code=0,
        output_snippet="def create_todo():\n    pass",
        error="",
        timestamp=time.time(),
    )


# ── Task Definitions ─────────────────────────────────────────────────────────


class TestBenchmarkTask:
    def test_task_creation(self):
        task = BenchmarkTask(
            id="test",
            category="python",
            name="Test Task",
            prompt="Write code",
            language="python",
        )
        assert task.id == "test"
        assert task.category == BenchmarkCategory.PYTHON
        assert task.name == "Test Task"
        assert task.prompt == "Write code"

    def test_task_with_string_category(self):
        task = BenchmarkTask(id="t", category="unknown_category", name="T", prompt="test")
        assert task.category == "unknown_category"

    def test_get_tasks_all(self):
        tasks = get_tasks()
        assert len(tasks) >= 30
        assert all(isinstance(t, BenchmarkTask) for t in tasks)

    def test_get_tasks_by_category(self):
        tasks = get_tasks(category="python")
        assert len(tasks) >= 3
        assert all(t.category == BenchmarkCategory.PYTHON for t in tasks)

    def test_get_tasks_by_language(self):
        tasks = get_tasks(language="rust")
        assert len(tasks) >= 1
        assert all(t.language == "rust" for t in tasks)

    def test_get_tasks_by_category_and_language(self):
        tasks = get_tasks(category="react", language="typescript")
        assert len(tasks) >= 2

    def test_get_categories(self):
        cats = get_categories()
        assert "python" in cats
        assert "rust" in cats
        assert "android" in cats
        assert "testing" in cats


# ── Quality Scoring ──────────────────────────────────────────────────────────


class TestQualityScoring:
    def test_empty_output(self):
        assert score_quality("", "python") == 0.0

    def test_all_checks_match(self):
        output = "def foo():\n    return 42\nclass Bar:\n    pass\nimport os\nprint('hi')"
        score = score_quality(output, "python")
        assert score > 0.5

    def test_no_matches(self):
        output = "This is not code at all, just a plain text paragraph."
        score = score_quality(output, "python")
        assert score < 0.5

    def test_language_specific_checks(self):
        output = "fn main() {\n    println!(\"hello\");\n}"
        score = score_quality(output, "rust")
        assert score > 0.3

    def test_length_bonus(self):
        short = "def foo(): pass"
        long = "def foo():\n    pass\n" * 200
        assert score_quality(long, "python") > score_quality(short, "python")

    def test_framework_specific(self):
        output = 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/")\ndef root():\n    return {"ok": True}'
        score = score_quality(output, "fastapi")
        assert score > 0.5


# ── BenchmarkResult ──────────────────────────────────────────────────────────


class TestBenchmarkResult:
    def test_result_creation(self, sample_result):
        r = sample_result
        assert r.task_id == "py_crud_api"
        assert r.provider_id == "forge"
        assert r.success is True
        assert r.duration_ms == 15000.0
        assert r.quality_score == 0.85


# ── Mock Provider ────────────────────────────────────────────────────────────


def _make_mock_provider(pid="forge", success=True, delay_ms=100, quality=0.8):
    from core.providers.base import ExecutionProvider, ProviderCapabilities, ProviderHealth, ProviderHealthStatus, ExecutionResult

    p_id = pid
    p_success = success
    p_delay = delay_ms

    class MockProvider(ExecutionProvider):
        provider_id = p_id
        name = p_id.title()
        version = "1.0"
        priority = 50
        installed = True
        _enabled = True

        def capabilities(self):
            return ProviderCapabilities(capability_names=["coding", "python", "javascript"])

        async def health(self):
            return ProviderHealth(status=ProviderHealthStatus.HEALTHY)

        async def execute(self, task, context=None):
            if not p_success:
                return ExecutionResult(success=False, output="", error="failed")
            output = f"def {p_id}_function():\n    return 42\nclass Result:\n    pass\nimport os\nprint('done')"
            return ExecutionResult(success=True, output=output, duration_ms=p_delay)

    return MockProvider()


# ── BenchmarkRunner ──────────────────────────────────────────────────────────


class TestBenchmarkRunner:
    @pytest.mark.asyncio
    async def test_run_task_success(self, store):
        provider = _make_mock_provider("forge", success=True, delay_ms=100)
        runner = BenchmarkRunner(store=store)
        task = get_tasks(category="python")[0]
        result = await runner.run_task(task, provider)
        assert result.success is True
        assert result.provider_id == "forge"
        assert result.task_id == task.id
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_run_task_failure(self, store):
        provider = _make_mock_provider("forge", success=False)
        runner = BenchmarkRunner(store=store)
        task = get_tasks(category="python")[0]
        result = await runner.run_task(task, provider)
        assert result.success is False
        assert result.provider_id == "forge"

    @pytest.mark.asyncio
    async def test_run_task_crash(self, store):
        from core.providers.base import ExecutionProvider
        provider = _make_mock_provider("crashy")
        original = provider.execute

        async def crashy(task, ctx=None):
            raise RuntimeError("Unexpected crash!")

        provider.execute = crashy
        runner = BenchmarkRunner(store=store)
        task = get_tasks(category="python")[0]
        result = await runner.run_task(task, provider)
        assert result.success is False
        assert result.crash is True
        assert "crash" in result.error.lower()

    @pytest.mark.asyncio
    async def test_run_task_timeout(self, store):
        provider = _make_mock_provider("slow", success=True)

        async def slow(task, ctx=None):
            import asyncio
            await asyncio.sleep(0.5)
            raise asyncio.TimeoutError()

        provider.execute = slow
        runner = BenchmarkRunner(store=store)
        task = get_tasks(category="python")[0]
        task.timeout = 0.1
        result = await runner.run_task(task, provider)
        assert result.success is False
        assert result.error == "timeout"

    @pytest.mark.asyncio
    async def test_run_provider_saves_to_store(self, store):
        provider = _make_mock_provider("forge", success=True)
        runner = BenchmarkRunner(store=store)
        results = await runner.run_provider(provider, category="python")
        assert len(results) >= 3
        saved = store.get_results(provider_id="forge")
        assert len(saved) >= 3

    @pytest.mark.asyncio
    async def test_run_provider_feeds_memory(self, store):
        from core.providers.memory import provider_memory
        provider_memory._records.clear()
        provider = _make_mock_provider("forge_mem_test", success=True)
        runner = BenchmarkRunner(store=store)
        results = await runner.run_provider(provider, category="python")
        record = provider_memory.get_record("forge_mem_test")
        assert record is not None
        assert record.total_executions >= 3

    @pytest.mark.asyncio
    async def test_run_all_multiple_providers(self, store):
        p1 = _make_mock_provider("forge", success=True)
        p2 = _make_mock_provider("codex", success=False)
        runner = BenchmarkRunner(store=store)
        all_results = await runner.run_all([p1, p2], category="python")
        assert "forge" in all_results
        assert "codex" in all_results
        assert len(all_results["forge"]) >= 3
        assert len(all_results["codex"]) >= 3


# ── BenchmarkStore ───────────────────────────────────────────────────────────


class TestBenchmarkStore:
    def test_save_and_get_result(self, store, sample_result):
        store.save_result(sample_result)
        results = store.get_results(provider_id="forge")
        assert len(results) == 1
        assert results[0]["task_id"] == "py_crud_api"
        assert results[0]["success"] == 1

    def test_save_multiple(self, store, sample_result):
        r2 = BenchmarkResult(
            task_id="java_class_model", provider_id="forge", category="java",
            language="java", framework="", success=True, duration_ms=20000.0,
            quality_score=0.9, timestamp=time.time(),
        )
        store.save_result(sample_result)
        store.save_result(r2)
        results = store.get_results(provider_id="forge")
        assert len(results) == 2

    def test_save_results_batch(self, store):
        results = [
            BenchmarkResult(task_id=f"task_{i}", provider_id="forge", category="python",
                           language="python", framework="", success=True,
                           duration_ms=1000.0 * i, quality_score=0.8, timestamp=time.time())
            for i in range(5)
        ]
        store.save_results(results)
        saved = store.get_results(provider_id="forge")
        assert len(saved) == 5

    def test_get_results_filtered(self, store, sample_result):
        store.save_result(sample_result)
        r2 = BenchmarkResult(
            task_id="java_class_model", provider_id="forge", category="java",
            language="java", framework="", success=True, duration_ms=20000.0,
            quality_score=0.9, timestamp=time.time(),
        )
        store.save_result(r2)
        java_results = store.get_results(category="java")
        assert len(java_results) == 1
        python_results = store.get_results(category="python")
        assert len(python_results) == 1

    def test_get_results_by_language(self, store, sample_result):
        store.save_result(sample_result)
        r = store.get_results(language="python")
        assert len(r) >= 1

    def test_get_summary(self, store):
        results = [
            BenchmarkResult(task_id=f"task_{i}", provider_id="forge", category="python",
                           language="python", framework="", success=True if i < 3 else False,
                           duration_ms=1000.0, quality_score=0.8, timestamp=time.time())
            for i in range(4)
        ]
        store.save_results(results)
        summaries = store.get_summary(provider_id="forge")
        assert len(summaries) >= 1
        s = summaries[0]
        assert s.total_runs == 4
        assert s.success_count == 3
        assert s.success_rate == 0.75

    def test_get_summary_by_category(self, store):
        results = [
            BenchmarkResult(task_id="t1", provider_id="forge", category="python", language="python",
                           framework="", success=True, duration_ms=1000.0, quality_score=0.8, timestamp=time.time()),
            BenchmarkResult(task_id="t2", provider_id="forge", category="java", language="java",
                           framework="", success=False, duration_ms=2000.0, quality_score=0.5, timestamp=time.time()),
        ]
        store.save_results(results)
        python_summary = store.get_summary(provider_id="forge", category="python")
        assert len(python_summary) == 1
        assert python_summary[0].category == "python"
        assert python_summary[0].success_rate == 1.0

    def test_get_best_provider(self, store):
        store.save_results([
            BenchmarkResult(task_id="t1", provider_id="forge", category="python", language="python",
                           framework="", success=True, duration_ms=1000.0, quality_score=0.9, timestamp=time.time()),
            BenchmarkResult(task_id="t2", provider_id="forge", category="python", language="python",
                           framework="", success=True, duration_ms=1500.0, quality_score=0.85, timestamp=time.time()),
            BenchmarkResult(task_id="t3", provider_id="codex", category="python", language="python",
                           framework="", success=True, duration_ms=2000.0, quality_score=0.7, timestamp=time.time()),
            BenchmarkResult(task_id="t4", provider_id="codex", category="python", language="python",
                           framework="", success=False, duration_ms=3000.0, quality_score=0.6, timestamp=time.time()),
        ])
        best = store.get_best_provider("python")
        assert best is not None
        assert best["provider_id"] == "forge"

    def test_get_best_provider_no_data(self, store):
        best = store.get_best_provider("nonexistent")
        assert best is None

    def test_get_leaderboard(self, store):
        store.save_results([
            BenchmarkResult(task_id="t1", provider_id="forge", category="python", language="python",
                           framework="", success=True, duration_ms=1000.0, quality_score=0.9, timestamp=time.time()),
            BenchmarkResult(task_id="t2", provider_id="forge", category="python", language="python",
                           framework="", success=True, duration_ms=1500.0, quality_score=0.85, timestamp=time.time()),
            BenchmarkResult(task_id="t3", provider_id="codex", category="python", language="python",
                           framework="", success=True, duration_ms=2000.0, quality_score=0.7, timestamp=time.time()),
            BenchmarkResult(task_id="t4", provider_id="codex", category="python", language="python",
                           framework="", success=True, duration_ms=3000.0, quality_score=0.6, timestamp=time.time()),
        ])
        lb = store.get_leaderboard()
        assert len(lb) >= 2
        assert lb[0]["provider_id"] == "forge"

    def test_get_leaderboard_filtered(self, store):
        store.save_results([
            BenchmarkResult(task_id="t1", provider_id="forge", category="python", language="python",
                           framework="", success=True, duration_ms=1000.0, quality_score=0.9, timestamp=time.time()),
            BenchmarkResult(task_id="t2", provider_id="forge", category="python", language="python",
                           framework="", success=True, duration_ms=1000.0, quality_score=0.9, timestamp=time.time()),
            BenchmarkResult(task_id="t3", provider_id="forge", category="java", language="java",
                           framework="", success=True, duration_ms=1000.0, quality_score=0.9, timestamp=time.time()),
            BenchmarkResult(task_id="t4", provider_id="forge", category="java", language="java",
                           framework="", success=True, duration_ms=1000.0, quality_score=0.9, timestamp=time.time()),
        ])
        lb = store.get_leaderboard(category="java")
        assert len(lb) == 1
        assert lb[0]["category"] == "java"

    def test_clear(self, store, sample_result):
        store.save_result(sample_result)
        store.clear()
        results = store.get_results()
        assert len(results) == 0

    def test_get_stats(self, store, sample_result):
        stats = store.get_stats()
        assert stats["total_runs"] == 0
        assert stats["categories"] == 0
        store.save_result(sample_result)
        stats = store.get_stats()
        assert stats["total_runs"] == 1
        assert stats["providers"] == 1
        assert stats["categories"] == 1

    def test_durability(self, store, sample_result):
        store.save_result(sample_result)
        # Create new store instance at same path
        store2 = BenchmarkStore(db_path=store._db_path)
        results = store2.get_results(provider_id="forge")
        assert len(results) == 1


# ── BenchmarkSummary ─────────────────────────────────────────────────────────


class TestBenchmarkSummary:
    def test_summary_defaults(self):
        s = BenchmarkSummary()
        assert s.total_runs == 0
        assert s.success_rate == 0.0
        assert s.avg_quality == 0.0

    def test_summary_with_values(self):
        s = BenchmarkSummary(
            provider_id="forge", category="python", language="python",
            total_runs=10, success_count=8, success_rate=0.8,
            avg_duration_ms=1500.0, avg_quality=0.85,
        )
        assert s.provider_id == "forge"
        assert s.success_rate == 0.8
        assert s.avg_quality == 0.85


# ── Singleton ────────────────────────────────────────────────────────────────


class TestBenchmarkSingletons:
    def test_benchmark_store_singleton_exists(self):
        from core.providers.benchmark_store import benchmark_store
        assert benchmark_store is not None

    def test_tasks_is_defined(self):
        assert len(TASKS) >= 30

    def test_categories_exist(self):
        cats = get_categories()
        assert len(cats) >= 15
