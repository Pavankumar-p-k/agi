"""Multi-Model Benchmark — data models for benchmark runs, comparisons, and reports.

Usage:
  Runs a matrix of models x modes x tasks to measure:

    Capability = Model x Architecture

  Mode A (raw): Model only — no planner, no workflow engine.
  Mode B (+Arch): Model + full JARVIS architecture.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class BenchmarkMode(str, Enum):
    """Whether the architecture stack is active."""

    RAW = "raw"
    """Model only — direct LLM call, no planner/workflow/memory."""

    WITH_ARCHITECTURE = "with_architecture"
    """Model + full JARVIS architecture stack."""


class BenchmarkTaskCategory(str, Enum):
    """Category of benchmark task."""

    MULTI_STEP = "multi_step"
    RESEARCH = "research"
    RECOVERY = "recovery"
    COMPENSATION = "compensation"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"


class RunStatus(str, Enum):
    """Outcome of a single benchmark run."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


# ── Model Configuration ─────────────────────────────────────────────


@dataclass
class ModelConfiguration:
    """Configuration for a model under test.

    Attributes:
        id: unique identifier (e.g. "qwen2.5:7b")
        name: human-readable name (e.g. "Qwen 2.5 7B")
        provider: llm provider (ollama, openai, anthropic, ...)
        endpoint: API URL or endpoint identifier
        max_tokens: max generation tokens
        temperature: generation temperature
    """

    id: str
    name: str
    provider: str = "ollama"
    endpoint: str = "http://localhost:11434"
    max_tokens: int = 4096
    temperature: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "endpoint": self.endpoint,
        }


# ── Benchmark Task ──────────────────────────────────────────────────


@dataclass
class BenchmarkTask:
    """A single benchmark task definition.

    Attributes:
        id: unique task identifier (e.g. "A", "B")
        name: human-readable label
        goal: the natural-language goal prompt
        category: task category
        required_tools: tools that must appear for success
        expected_tools: full set of expected tools (for tool accuracy)
        timeout_seconds: max execution time
    """

    id: str
    name: str
    goal: str
    category: BenchmarkTaskCategory = BenchmarkTaskCategory.MULTI_STEP
    required_tools: list[str] = field(default_factory=list)
    expected_tools: list[str] = field(default_factory=list)
    timeout_seconds: int = 300

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "goal": self.goal[:100],
            "category": self.category.value,
            "required_tools": self.required_tools,
            "timeout_seconds": self.timeout_seconds,
        }


# ── Benchmark Run ───────────────────────────────────────────────────


@dataclass
class BenchmarkRun:
    """Result of a single model x mode x task execution.

    Attributes:
        run_id: unique run identifier
        model_id: which model (matches ModelConfiguration.id)
        task_id: which task (matches BenchmarkTask.id)
        mode: raw or with_architecture
        status: passed/failed/error/timeout/skipped
        metrics: dictionary of measured metrics
        elapsed_seconds: wall-clock time
        tool_names: ordered list of tools called
        hallucinated_tools: tools called that aren't in expected set
        missing_steps: required tools that were never called
        completed_naturally: whether LLM completed without planner enforcement
        loop_count: number of detected loops
        error_message: error details if status is error
        started_at: timestamp when run started
        finished_at: timestamp when run finished
    """

    run_id: str = ""
    model_id: str = ""
    task_id: str = ""
    mode: BenchmarkMode = BenchmarkMode.RAW
    status: RunStatus = RunStatus.SKIPPED
    metrics: dict[str, float] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    tool_names: list[str] = field(default_factory=list)
    hallucinated_tools: list[str] = field(default_factory=list)
    missing_steps: list[str] = field(default_factory=list)
    completed_naturally: bool = False
    loop_count: int = 0
    error_message: str = ""
    started_at: str = ""
    finished_at: str = ""

    def __post_init__(self):
        if not self.run_id:
            self.run_id = f"run_{uuid.uuid4().hex[:12]}"

    @property
    def is_success(self) -> bool:
        return self.status == RunStatus.PASSED

    @property
    def tool_accuracy(self) -> float:
        if not self.tool_names:
            return 0.0
        return sum(1 for t in self.tool_names if t not in self.hallucinated_tools)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model_id": self.model_id,
            "task_id": self.task_id,
            "mode": self.mode.value,
            "status": self.status.value,
            "metrics": self.metrics,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "tool_count": len(self.tool_names),
            "hallucinated_count": len(self.hallucinated_tools),
            "missing_count": len(self.missing_steps),
            "completed_naturally": self.completed_naturally,
            "loop_count": self.loop_count,
            "error": self.error_message[:200] if self.error_message else "",
        }


# ── Aggregated Results ──────────────────────────────────────────────


@dataclass
class ModelResult:
    """Aggregated results for a single model across tasks and modes.

    Attributes:
        model_config: the model configuration
        raw_runs: list of BenchmarkRun in RAW mode
        arch_runs: list of BenchmarkRun in WITH_ARCHITECTURE mode
        raw_success_rate: fraction of raw runs passed
        arch_success_rate: fraction of architecture runs passed
        average_gain: arch_success_rate - raw_success_rate
    """

    model_config: ModelConfiguration
    raw_runs: list[BenchmarkRun] = field(default_factory=list)
    arch_runs: list[BenchmarkRun] = field(default_factory=list)

    @property
    def raw_success_rate(self) -> float:
        if not self.raw_runs:
            return 0.0
        return sum(1 for r in self.raw_runs if r.is_success) / len(self.raw_runs)

    @property
    def arch_success_rate(self) -> float:
        if not self.arch_runs:
            return 0.0
        return sum(1 for r in self.arch_runs if r.is_success) / len(self.arch_runs)

    @property
    def average_gain(self) -> float:
        return self.arch_success_rate - self.raw_success_rate

    @property
    def raw_avg_elapsed(self) -> float:
        if not self.raw_runs:
            return 0.0
        return sum(r.elapsed_seconds for r in self.raw_runs) / len(self.raw_runs)

    @property
    def arch_avg_elapsed(self) -> float:
        if not self.arch_runs:
            return 0.0
        return sum(r.elapsed_seconds for r in self.arch_runs) / len(self.arch_runs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model_config.name,
            "model_id": self.model_config.id,
            "raw_success": round(self.raw_success_rate, 3),
            "arch_success": round(self.arch_success_rate, 3),
            "gain": round(self.average_gain, 3),
            "raw_elapsed": round(self.raw_avg_elapsed, 2),
            "arch_elapsed": round(self.arch_avg_elapsed, 2),
        }


@dataclass
class BenchmarkReport:
    """Full benchmark report across all models.

    Attributes:
        model_results: per-model aggregated results
        tasks: list of task definitions used
        generated_at: when the report was generated
        overall_avg_gain: average gain across all models
        overall_avg_raw: average raw success rate
        overall_avg_arch: average architecture success rate
    """

    model_results: list[ModelResult] = field(default_factory=list)
    tasks: list[BenchmarkTask] = field(default_factory=list)
    generated_at: datetime | None = None

    @property
    def overall_avg_gain(self) -> float:
        if not self.model_results:
            return 0.0
        return sum(m.average_gain for m in self.model_results) / len(self.model_results)

    @property
    def overall_avg_raw(self) -> float:
        if not self.model_results:
            return 0.0
        return sum(m.raw_success_rate for m in self.model_results) / len(self.model_results)

    @property
    def overall_avg_arch(self) -> float:
        if not self.model_results:
            return 0.0
        return sum(m.arch_success_rate for m in self.model_results) / len(self.model_results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "tasks": [t.to_dict() for t in self.tasks],
            "models": [m.to_dict() for m in self.model_results],
            "overall_avg_raw": round(self.overall_avg_raw, 3),
            "overall_avg_arch": round(self.overall_avg_arch, 3),
            "overall_avg_gain": round(self.overall_avg_gain, 3),
        }

    def markdown_table(self) -> str:
        """Generate a markdown comparison table."""
        lines = [
            "| Model | Raw | +Architecture | Gain |",
            "|-------|-----|---------------|------|",
        ]
        for m in sorted(
            self.model_results,
            key=lambda x: x.average_gain,
            reverse=True,
        ):
            raw = f"{m.raw_success_rate:.0%}"
            arch = f"{m.arch_success_rate:.0%}"
            gain = f"+{m.average_gain:.0%}" if m.average_gain > 0 else f"{m.average_gain:.0%}"
            lines.append(f"| {m.model_config.name} | {raw} | {arch} | {gain} |")

        lines.append("")
        lines.append(f"**Average architecture gain: +{self.overall_avg_gain:.0%}**")
        return "\n".join(lines)
