"""Benchmark Orchestrator — runs the full model x mode x task matrix.

Given a list of models, tasks, and modes, the orchestrator:
  1. Creates adapters for each model
  2. Runs every combination (model x mode x task)
  3. Aggregates results into a BenchmarkReport
  4. Handles parallelism, error tolerance, and timeouts
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from core.benchmark.adapters import ModelAdapter, create_adapter
from core.benchmark.models import (
    BenchmarkMode,
    BenchmarkReport,
    BenchmarkRun,
    BenchmarkTask,
    ModelConfiguration,
    ModelResult,
    RunStatus,
)
from core.benchmark.runner import BenchmarkRunner

logger = logging.getLogger(__name__)


# ── Default Task Definitions ────────────────────────────────────────

# Mirrors the benchmarks/autonomous_workflow_benchmark.py tasks
DEFAULT_TASKS: list[BenchmarkTask] = [
    BenchmarkTask(
        id="A",
        name="Research → Build → Validate → Email",
        goal=(
            "Build a professional bookstore website and email the results. "
            "First research bookstore website designs and features. "
            "Then build the project, run tests, validate, and email the build report."
        ),
        required_tools=["browser_navigate", "build_project", "run_tests", "send_email"],
        expected_tools=["browser_navigate", "browser_snapshot", "build_project",
                        "run_tests", "runtime_validate", "send_email"],
    ),
    BenchmarkTask(
        id="B",
        name="Research → Android APK Delivery",
        goal=(
            "Build an Android coffee shop app and deliver the APK. "
            "Research coffee shop app UI trends first. "
            "Then build the project, repair any issues, validate runtime, "
            "and email the APK file as an attachment."
        ),
        required_tools=["browser_navigate", "build_project", "send_email"],
        expected_tools=["browser_navigate", "build_project", "send_email"],
    ),
    BenchmarkTask(
        id="C",
        name="Long-Running Recovery",
        goal=(
            "Build a calculator app, then recover from a crash "
            "and resume execution without duplicating previous steps."
        ),
        required_tools=["build_project"],
        expected_tools=["build_project", "run_tests", "send_email"],
    ),
]

# ── Default Model Configurations ────────────────────────────────────

DEFAULT_MODELS: list[ModelConfiguration] = [
    ModelConfiguration(id="qwen2.5:7b", name="Qwen 2.5 7B", provider="ollama"),
    ModelConfiguration(id="gemma4:9b", name="Gemma 4 9B", provider="ollama"),
    ModelConfiguration(id="llama3.1:8b", name="Llama 3.1 8B", provider="ollama"),
    ModelConfiguration(id="mistral:7b", name="Mistral 7B", provider="ollama"),
]


# ── Orchestrator ────────────────────────────────────────────────────


class BenchmarkOrchestrator:
    """Orchestrates the full benchmark matrix.

    Usage:
        orchestrator = BenchmarkOrchestrator()
        report = await orchestrator.run_all(
            models=[...],
            tasks=[...],
            include_raw=True,
            include_arch=True,
        )
        print(report.markdown_table())
    """

    def __init__(self, concurrency: int = 2, verbose: bool = False):
        self.concurrency = concurrency
        self.verbose = verbose

    async def run_all(
        self,
        models: list[ModelConfiguration] | None = None,
        tasks: list[BenchmarkTask] | None = None,
        include_raw: bool = True,
        include_arch: bool = True,
    ) -> BenchmarkReport:
        """Run the full benchmark matrix.

        Args:
            models: list of model configurations (defaults to DEFAULT_MODELS)
            tasks: list of tasks (defaults to DEFAULT_TASKS)
            include_raw: whether to run in RAW mode
            include_arch: whether to run in WITH_ARCHITECTURE mode

        Returns:
            BenchmarkReport with per-model comparisons
        """
        models = models or DEFAULT_MODELS
        tasks = tasks or DEFAULT_TASKS
        modes: list[BenchmarkMode] = []
        if include_raw:
            modes.append(BenchmarkMode.RAW)
        if include_arch:
            modes.append(BenchmarkMode.WITH_ARCHITECTURE)

        if not modes:
            raise ValueError("At least one mode must be enabled")

        logger.info(
            "Starting benchmark: %d models x %d tasks x %d modes",
            len(models), len(tasks), len(modes),
        )

        # Build all combinations
        jobs: list[dict[str, Any]] = []
        for model in models:
            adapter = create_adapter(
                model_id=model.id,
                provider=model.provider,
                endpoint=model.endpoint,
                max_tokens=model.max_tokens,
                temperature=model.temperature,
            )
            runner = BenchmarkRunner(adapter)
            for task in tasks:
                for mode in modes:
                    jobs.append({
                        "model": model,
                        "task": task,
                        "mode": mode,
                        "runner": runner,
                        "adapter": adapter,
                    })

        logger.info("Total jobs: %d", len(jobs))

        # Run with bounded concurrency
        sem = asyncio.Semaphore(self.concurrency)
        runs: list[BenchmarkRun] = []

        async def _run_job(job: dict[str, Any]) -> BenchmarkRun:
            async with sem:
                run = await job["runner"].execute(job["task"], mode=job["mode"])
                if self.verbose:
                    logger.info(
                        "  [%s] %s (%s) → %s (%.1fs)",
                        run.model_id, run.task_id, run.mode.value,
                        run.status.value, run.elapsed_seconds,
                    )
                return run

        results = await asyncio.gather(
            *[_run_job(j) for j in jobs],
            return_exceptions=True,
        )

        for r in results:
            if isinstance(r, BenchmarkRun):
                runs.append(r)
            elif isinstance(r, Exception):
                logger.error("Job failed: %s", r)

        # Aggregate by model
        model_results: list[ModelResult] = []
        for model in models:
            raw_runs = [r for r in runs if r.model_id == model.id and r.mode == BenchmarkMode.RAW]
            arch_runs = [r for r in runs if r.model_id == model.id and r.mode == BenchmarkMode.WITH_ARCHITECTURE]
            model_results.append(ModelResult(
                model_config=model,
                raw_runs=raw_runs,
                arch_runs=arch_runs,
            ))

        return BenchmarkReport(
            model_results=model_results,
            tasks=tasks,
            generated_at=datetime.now(timezone.utc),
        )

    async def run_single(
        self,
        model: ModelConfiguration,
        task: BenchmarkTask,
        modes: list[BenchmarkMode] | None = None,
    ) -> dict[str, BenchmarkRun]:
        """Run a single model on a single task in specified modes.

        Returns:
            Dict mapping mode value to BenchmarkRun
        """
        modes = modes or [BenchmarkMode.RAW, BenchmarkMode.WITH_ARCHITECTURE]
        adapter = create_adapter(
            model_id=model.id,
            provider=model.provider,
            endpoint=model.endpoint,
        )
        runner = BenchmarkRunner(adapter)

        results: dict[str, BenchmarkRun] = {}
        for mode in modes:
            run = await runner.execute(task, mode=mode)
            results[mode.value] = run
            logger.info(
                "  %s %s (%s): %s (%.1fs)",
                model.name, task.id, mode.value, run.status.value, run.elapsed_seconds,
            )
        return results
