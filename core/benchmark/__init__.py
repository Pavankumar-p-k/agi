"""Multi-Model Benchmark Harness (Phase BM).

Measures:

    Capability = Model × Architecture

by running identical tasks across multiple models in two modes:
  - RAW: model only, no architecture stack
  - WITH_ARCHITECTURE: model + full JARVIS pipeline

Usage:
    from core.benchmark import (
        BenchmarkOrchestrator,
        BenchmarkReportGenerator,
        BenchmarkResultsStore,
        BenchmarkTask, BenchmarkMode,
        ModelConfiguration,
        create_adapter,
    )

    orchestrator = BenchmarkOrchestrator()
    report = await orchestrator.run_all()
    print(BenchmarkReportGenerator.to_markdown(report))
"""

from core.benchmark.adapters import (
    AnthropicAdapter,
    ModelAdapter,
    OllamaAdapter,
    OpenAIAdapter,
    create_adapter,
)
from core.benchmark.models import (
    BenchmarkMode,
    BenchmarkReport,
    BenchmarkRun,
    BenchmarkTask,
    BenchmarkTaskCategory,
    ModelConfiguration,
    ModelResult,
    RunStatus,
)
from core.benchmark.orchestrator import (
    DEFAULT_MODELS,
    DEFAULT_TASKS,
    BenchmarkOrchestrator,
)
from core.benchmark.report_generator import BenchmarkReportGenerator
from core.benchmark.results_store import BenchmarkResultsStore
from core.benchmark.runner import BenchmarkRunner

__all__ = [
    "AnthropicAdapter",
    "BenchmarkMode",
    "BenchmarkOrchestrator",
    "BenchmarkReport",
    "BenchmarkReportGenerator",
    "BenchmarkResultsStore",
    "BenchmarkRun",
    "BenchmarkRunner",
    "BenchmarkTask",
    "BenchmarkTaskCategory",
    "DEFAULT_MODELS",
    "DEFAULT_TASKS",
    "ModelAdapter",
    "ModelConfiguration",
    "ModelResult",
    "OllamaAdapter",
    "OpenAIAdapter",
    "RunStatus",
    "create_adapter",
]
