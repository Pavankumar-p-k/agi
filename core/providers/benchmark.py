"""Provider Benchmark Suite: measure real provider quality on standard tasks.

Completed from the committed contract in tests/unit/test_provider_benchmark.py.

- ``TASKS``: ≥30 BenchmarkTasks across ≥15 categories (python, rust, react,
  android, testing, ...).
- ``score_quality``: cheap structural heuristics over generated output —
  not a judge, a smoke signal (0.0 empty → up to 1.0 for rich, matching code).
- ``BenchmarkRunner``: executes tasks against providers, tolerates crashes
  and timeouts honestly (crash=True / error="timeout"), persists results via
  BenchmarkStore and feeds the shared provider memory.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BenchmarkCategory(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    REACT = "react"
    RUST = "rust"
    GO = "go"
    JAVA = "java"
    KOTLIN = "kotlin"
    ANDROID = "android"
    TESTING = "testing"
    REFACTORING = "refactoring"
    DEBUGGING = "debugging"
    DOCS = "docs"
    DEVOPS = "devops"
    DATABASE = "database"
    API = "api"
    SECURITY = "security"
    CLI = "cli"
    DATA = "data"


@dataclass
class BenchmarkTask:
    id: str
    category: Any  # BenchmarkCategory or free string (kept honest, not coerced blindly)
    name: str
    prompt: str
    language: str = ""
    framework: str = ""
    timeout: float = 120.0

    def __post_init__(self) -> None:
        try:
            self.category = BenchmarkCategory(str(self.category))
        except ValueError:
            self.category = str(self.category)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value if isinstance(self.category, BenchmarkCategory) else self.category,
            "name": self.name,
            "prompt": self.prompt,
            "language": self.language,
            "framework": self.framework,
            "timeout": self.timeout,
        }


@dataclass
class BenchmarkResult:
    task_id: str
    provider_id: str
    category: str
    language: str = ""
    framework: str = ""
    success: bool = False
    duration_ms: float = 0.0
    quality_score: float = 0.0
    retries: int = 0
    crash: bool = False
    cost: float = 0.0
    tokens_used: int = 0
    exit_code: int = 0
    output_snippet: str = ""
    error: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "provider_id": self.provider_id,
            "category": self.category,
            "language": self.language,
            "framework": self.framework,
            "success": 1 if self.success else 0,
            "duration_ms": self.duration_ms,
            "quality_score": self.quality_score,
            "retries": self.retries,
            "crash": 1 if self.crash else 0,
            "cost": self.cost,
            "tokens_used": self.tokens_used,
            "exit_code": self.exit_code,
            "output_snippet": self.output_snippet,
            "error": self.error,
            "timestamp": self.timestamp,
        }


# --------------------------------------------------------------------------- #
# Task library (30+ tasks, 15+ categories)                                    #
# --------------------------------------------------------------------------- #

TASKS: list[BenchmarkTask] = [
    BenchmarkTask("py_crud_api", "python", "Python CRUD API", "Implement a small CRUD API module with input validation.", "python"),
    BenchmarkTask("py_class_model", "python", "Python Class Model", "Implement a dataclass-backed domain model with methods.", "python"),
    BenchmarkTask("py_file_util", "python", "Python File Utility", "Write a utility that reads, transforms, and writes text files safely.", "python"),
    BenchmarkTask("py_async_worker", "python", "Async Worker", "Implement an asyncio worker pool with graceful shutdown.", "python"),
    BenchmarkTask("py_cli_tool", "python", "Python CLI Tool", "Implement an argparse-based CLI with subcommands.", "python"),
    BenchmarkTask("js_dom_helper", "javascript", "JS DOM Helper", "Write a DOM helper module with event delegation.", "javascript"),
    BenchmarkTask("js_promise_queue", "javascript", "JS Promise Queue", "Implement a concurrency-limited promise queue.", "javascript"),
    BenchmarkTask("js_module_utils", "javascript", "JS Module Utils", "Write ES-module utility functions for arrays and objects.", "javascript"),
    BenchmarkTask("ts_typed_service", "typescript", "Typed Service", "Implement a strongly-typed service class with generics.", "typescript"),
    BenchmarkTask("ts_type_guards", "typescript", "Type Guards", "Write type guards and discriminated-union handling.", "typescript"),
    BenchmarkTask("react_todo_list", "react", "React Todo List", "Implement a React todo-list component with hooks and types.", language="typescript", framework="react"),
    BenchmarkTask("react_data_table", "react", "React Data Table", "Implement a sortable, paginated React data table component.", language="typescript", framework="react"),
    BenchmarkTask("react_form_hook", "react", "React Form Hook", "Implement a custom React form hook with validation.", language="typescript", framework="react"),
    BenchmarkTask("rust_cli_parse", "rust", "Rust CLI Parse", "Implement a Rust CLI argument parser without external crates.", "rust"),
    BenchmarkTask("rust_error_types", "rust", "Rust Error Types", "Define a Rust error enum with From conversions and Result flow.", "rust"),
    BenchmarkTask("go_http_server", "go", "Go HTTP Server", "Implement a small net/http server with JSON handlers.", "go"),
    BenchmarkTask("go_worker_pool", "go", "Go Worker Pool", "Implement a goroutine worker pool with channels.", "go"),
    BenchmarkTask("java_class_model", "java", "Java Class Model", "Implement a Java domain model with builder and equals/hashCode.", "java"),
    BenchmarkTask("kotlin_android_screen", "android", "Android Screen", "Implement an Android Activity screen with view binding in Kotlin.", language="kotlin"),
    BenchmarkTask("kotlin_viewmodel", "android", "Android ViewModel", "Implement an Android ViewModel with LiveData in Kotlin.", language="kotlin"),
    BenchmarkTask("test_py_unit", "testing", "Python Unit Tests", "Write pytest unit tests for a given module, including edge cases.", "python", framework="pytest"),
    BenchmarkTask("test_js_jest", "testing", "JS Jest Tests", "Write Jest tests for a JavaScript module with mocks.", "javascript", framework="jest"),
    BenchmarkTask("refactor_extract_fn", "refactoring", "Extract Function", "Refactor a long function by extracting cohesive helpers.", "python"),
    BenchmarkTask("debug_off_by_one", "debugging", "Off-by-one Fix", "Locate and fix an off-by-one bug in a loop.", "python"),
    BenchmarkTask("docs_readme", "docs", "README Authoring", "Write a README with usage, install, and examples sections.", "markdown"),
    BenchmarkTask("devops_dockerfile", "devops", "Dockerfile", "Write a multi-stage Dockerfile for a Python service.", "dockerfile"),
    BenchmarkTask("db_sql_migration", "database", "SQL Migration", "Write a SQL migration adding a table with indexes and constraints.", "sql"),
    BenchmarkTask("api_openapi_spec", "api", "OpenAPI Spec", "Author an OpenAPI 3 spec for a small REST API.", "yaml"),
    BenchmarkTask("sec_input_validation", "security", "Input Validation", "Harden an input-handling function against injection and overflow.", "python"),
    BenchmarkTask("cli_argparse", "cli", "CLI Argument Parsing", "Implement robust CLI parsing with validation and help text.", "python"),
    BenchmarkTask("data_csv_transform", "data", "CSV Transform", "Implement a streaming CSV transform with aggregation.", "python"),
    BenchmarkTask("ts_react_state", "react", "React State Store", "Implement a minimal external state store for React with hooks.", language="typescript", framework="react"),
]

assert len(TASKS) >= 30, "benchmark task library must hold 30+ tasks"


def get_tasks(
    category: Optional[str] = None,
    language: Optional[str] = None,
) -> list[BenchmarkTask]:
    """Return benchmark tasks, optionally filtered by category and/or language."""
    tasks = list(TASKS)
    if category is not None:
        tasks = [t for t in tasks if str(t.category.value if isinstance(t.category, BenchmarkCategory) else t.category) == str(category)]
    if language is not None:
        tasks = [t for t in tasks if t.language == language]
    return tasks


def get_categories() -> list[str]:
    """All distinct categories present in the task library."""
    seen: list[str] = []
    for t in TASKS:
        value = t.category.value if isinstance(t.category, BenchmarkCategory) else str(t.category)
        if value not in seen:
            seen.append(value)
    return seen


# --------------------------------------------------------------------------- #
# Quality scoring                                                             #
# --------------------------------------------------------------------------- #

_LANGUAGE_CHECKS: dict[str, list[str]] = {
    "python": [r"\bdef\s+\w+\s*\(", r"\bclass\s+\w+", r"^\s*import\s+\w+", r"\bprint\s*\(", r"\breturn\b"],
    "javascript": [r"\bfunction\s+\w+", r"\bconst\s+\w+", r"\bexport\b", r"=>", r"\breturn\b"],
    "typescript": [r"\bfunction\s+\w+", r":\s*(string|number|boolean|void)", r"\binterface\s+\w+", r"\bexport\b", r"\breturn\b"],
    "rust": [r"\bfn\s+\w+", r"println!", r"\blet\s+(mut\s+)?\w+", r"->", r"\bmatch\b"],
    "go": [r"\bfunc\s+\w+", r"fmt\.", r"\bpackage\s+\w+", r":=", r"\breturn\b"],
    "java": [r"\bclass\s+\w+", r"\bpublic\s+", r"\bprivate\s+", r"\breturn\b", r"new\s+\w+\("],
    "kotlin": [r"\bfun\s+\w+", r"\bclass\s+\w+", r"\bval\s+\w+", r"\breturn\b"],
    "fastapi": [r"from\s+fastapi\s+import", r"FastAPI\(\)", r"@app\.(get|post|put|delete)", r"\bdef\s+\w+", r"\breturn\b"],
    "sql": [r"\bCREATE\s+TABLE\b", r"\bPRIMARY\s+KEY\b", r"\bINDEX\b", r"\bNOT\s+NULL\b"],
    "dockerfile": [r"^FROM\s+", r"^RUN\s+", r"^CMD\s+", r"^COPY\s+"],
}

_DEFAULT_CHECKS = [r"\bdef\s+\w+", r"\bclass\s+\w+", r"\breturn\b"]


def score_quality(output: str, language: str = "") -> float:
    """Heuristic structural quality in [0, 1].

    0.0 for empty output; rises with language-idiomatic structure matched and
    a small length bonus.  Deliberately cheap and deterministic.
    """
    if not output or not output.strip():
        return 0.0

    key = (language or "").lower().strip()
    patterns = _LANGUAGE_CHECKS.get(key, _LANGUAGE_CHECKS.get(key.split("-")[0], _DEFAULT_CHECKS))
    matched = sum(1 for pattern in patterns if re.search(pattern, output, re.MULTILINE | re.IGNORECASE))
    base = matched / max(1, len(patterns))

    # Length bonus: rewards substantive implementations, saturates quickly.
    chars = len(output)
    length_bonus = min(0.2, chars / 20000.0)

    return round(min(1.0, base + length_bonus), 4)


# --------------------------------------------------------------------------- #
# Runner                                                                      #
# --------------------------------------------------------------------------- #

class BenchmarkRunner:
    """Runs benchmark tasks against providers and records honest results."""

    def __init__(self, store: Any = None) -> None:
        self.store = store

    async def run_task(self, task: BenchmarkTask, provider: Any) -> BenchmarkResult:
        category = task.category.value if isinstance(task.category, BenchmarkCategory) else str(task.category)
        result = BenchmarkResult(
            task_id=task.id,
            provider_id=getattr(provider, "provider_id", "unknown"),
            category=category,
            language=task.language,
            framework=task.framework,
        )
        started = time.perf_counter()
        try:
            timeout = float(getattr(task, "timeout", 0.0) or 0.0)
            if timeout > 0:
                exec_result = await asyncio.wait_for(
                    provider.execute({"task": task.prompt, "goal": task.prompt, "language": task.language}),
                    timeout=timeout,
                )
            else:
                exec_result = await provider.execute({"task": task.prompt, "goal": task.prompt, "language": task.language})
        except asyncio.TimeoutError:
            result.duration_ms = (time.perf_counter() - started) * 1000.0
            result.success = False
            result.error = "timeout"
            self._finish(task, result, provider)
            return result
        except Exception as exc:
            result.duration_ms = (time.perf_counter() - started) * 1000.0
            result.success = False
            result.crash = True
            result.error = f"crash: {exc}"
            self._finish(task, result, provider)
            return result

        result.duration_ms = (time.perf_counter() - started) * 1000.0
        output = getattr(exec_result, "output", "") or ""
        result.success = bool(getattr(exec_result, "success", False))
        result.error = getattr(exec_result, "error", "") or ""
        result.cost = float(getattr(exec_result, "cost", 0.0) or 0.0)
        result.tokens_used = int(getattr(exec_result, "tokens_used", 0) or 0)
        result.output_snippet = output[:400]
        result.quality_score = score_quality(output, task.language or task.framework or category)
        if not result.success and not result.error:
            result.error = "provider reported failure"
        self._finish(task, result, provider)
        return result

    def _finish(self, task: BenchmarkTask, result: BenchmarkResult, provider: Any) -> None:
        """Persist to the store and feed shared provider memory (never raises)."""
        try:
            if self.store is not None:
                self.store.save_result(result)
        except Exception as exc:
            logger.debug("[benchmark] store.save_result failed: %s", exc)
        try:
            from core.providers.memory import provider_memory
            provider_memory.record_execution(
                provider_id=result.provider_id,
                success=result.success,
                duration_ms=result.duration_ms,
                capability=result.category,
                language=result.language,
            )
        except Exception as exc:
            logger.debug("[benchmark] provider_memory feed failed: %s", exc)

    async def run_provider(self, provider: Any, category: Optional[str] = None) -> list[BenchmarkResult]:
        """Run all tasks (optionally one category) against a single provider."""
        results: list[BenchmarkResult] = []
        for task in get_tasks(category=category):
            results.append(await self.run_task(task, provider))
        return results

    async def run_all(self, providers: list[Any], category: Optional[str] = None) -> dict[str, list[BenchmarkResult]]:
        """Run tasks across multiple providers, grouped by provider_id."""
        all_results: dict[str, list[BenchmarkResult]] = {}
        for provider in providers:
            pid = getattr(provider, "provider_id", "unknown")
            all_results[pid] = await self.run_provider(provider, category=category)
        return all_results
