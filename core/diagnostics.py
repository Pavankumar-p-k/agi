"""Runtime and source diagnostics for JARVIS.

This module is intentionally dependency-light. It powers a doctor-style report
that explains degraded responses and crash risks without needing models,
network setup, or optional UI/voice packages.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "archive",
    "jarvis_launcher.egg-info",
    "data",
    "devtools",
    "reports",
}


@dataclass
class DiagnosticIssue:
    severity: str
    category: str
    path: str
    message: str
    fix: str


@dataclass
class DiagnosticReport:
    status: str
    root: str
    counts: dict[str, int] = field(default_factory=dict)
    optional_dependencies: dict[str, bool] = field(default_factory=dict)
    runtime_flags: dict[str, bool] = field(default_factory=dict)
    issues: list[DiagnosticIssue] = field(default_factory=list)
    capability_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["issues"] = [asdict(issue) for issue in self.issues]
        return data


def _iter_python_files(root: Path = ROOT) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        parts = set(path.relative_to(root).parts)
        if parts & IGNORED_DIRS:
            continue
        yield path


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _scan_python_file(path: Path, report: DiagnosticReport) -> None:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        report.issues.append(DiagnosticIssue(
            "medium",
            "source_read",
            _rel(path),
            f"Could not read file: {exc}",
            "Check file permissions or remove broken generated files.",
        ))
        return

    rel = _rel(path)
    lowered = text.lower()
    for marker, category in (
        ("notimplemented", "dead_code"),
        ("todo", "unfinished"),
        ("fixme", "unfinished"),
        ("placeholder", "fake_response"),
        ("dummy", "fake_response"),
        ("mock", "fake_response"),
    ):
        if marker in lowered:
            report.counts[category] = report.counts.get(category, 0) + lowered.count(marker)

    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        report.issues.append(DiagnosticIssue(
            "critical",
            "syntax",
            rel,
            f"Syntax error at line {exc.lineno}: {exc.msg}",
            "Fix the syntax error; this module cannot import.",
        ))
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                report.issues.append(DiagnosticIssue(
                    "medium",
                    "swallowed_exception",
                    f"{rel}:{node.lineno}",
                    "Exception is swallowed with bare pass, hiding real failure causes.",
                    "Log the exception or return a structured degraded result.",
                ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and all(isinstance(stmt, ast.Pass) for stmt in node.body):
                report.issues.append(DiagnosticIssue(
                    "low",
                    "empty_function",
                    f"{rel}:{node.lineno}",
                    f"{node.name} has no implementation.",
                    "Remove it if unused or implement the real behavior.",
                ))


def build_diagnostic_report(root: Path = ROOT) -> DiagnosticReport:
    report = DiagnosticReport(status="ok", root=str(root))
    py_files = list(_iter_python_files(root))
    report.counts["python_files"] = len(py_files)
    report.counts["tests"] = sum(1 for p in py_files if "test" in p.name.lower())

    optional_modules = [
        "fastapi",
        "uvicorn",
        "litellm",
        "httpx",
        "prompt_toolkit",
        "pygments",
        "selenium",
        "psutil",
        "cv2",
        "pynvml",
    ]
    report.optional_dependencies = {name: _has_module(name) for name in optional_modules}
    report.runtime_flags = {
        "openai_key": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY")),
        "gemini_key": bool(os.getenv("GEMINI_API_KEY")),
        "nvidia_key": bool(os.getenv("NVIDIA_API_KEY")),
        "force_cloud": os.getenv("FORCE_CLOUD", "").lower() in {"1", "true", "yes"},
        "python_3_11_plus": sys.version_info >= (3, 11),
    }

    for path in py_files:
        _scan_python_file(path, report)

    if not report.optional_dependencies.get("litellm", False):
        report.issues.append(DiagnosticIssue(
            "high",
            "missing_dependency",
            "core/llm_router.py",
            "LiteLLM is missing, so model calls can fail before routing/fallback logic runs.",
            "Install project dependencies or add a dependency-free direct Ollama fallback.",
        ))
    if not report.optional_dependencies.get("fastapi", False):
        report.issues.append(DiagnosticIssue(
            "critical",
            "missing_dependency",
            "core/main.py",
            "FastAPI is missing, so the backend server cannot start.",
            "Install server dependencies before running the API.",
        ))

    report.capability_gaps = [
        "OpenClaw has a typed plugin SDK and contract tests; Jarvis plugins are Python hooks with weaker boundary checks.",
        "OpenClaw has embedded agent attempt recovery, transcript repair, failover observation, and idle timeout breakers; Jarvis has partial supervisor/build loops but less recovery metadata.",
        "OpenClaw has detailed channel target resolution and durable outbound delivery; Jarvis channels exist but are less strongly normalized and audited.",
        "OpenClaw has broad security audit modules for plugins, filesystem, external content, and config flags; Jarvis now has doctor diagnostics but fewer policy-specific scanners.",
    ]

    severities = {issue.severity for issue in report.issues}
    if "critical" in severities:
        report.status = "critical"
    elif "high" in severities:
        report.status = "degraded"
    elif report.issues:
        report.status = "warning"
    return report
