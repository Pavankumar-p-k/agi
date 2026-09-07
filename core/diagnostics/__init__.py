"""Diagnostics helpers for startup and health reporting."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from dataclasses import dataclass, field
import sys
import importlib.util


@dataclass
class DiagnosticReport:
    status: str = "ok"
    counts: dict[str, int] = field(default_factory=dict)
    optional_dependencies: dict[str, bool] = field(default_factory=dict)
    runtime_flags: dict[str, bool] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    capability_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def build_diagnostic_report() -> DiagnosticReport:
    optional = {name: importlib.util.find_spec(name) is not None for name in ("fastapi", "numpy", "requests")}
    return DiagnosticReport(
        counts={"python_files": sum(1 for _ in Path(__file__).parents[1].rglob("*.py"))},
        optional_dependencies=optional,
        runtime_flags={"python_3_11_plus": sys.version_info >= (3, 11)},
        capability_gaps=["optional providers may be unavailable"],
    )


class BootStep:
    def __init__(self, name: str):
        self.name = name
        self.status = "ok"
        self.detail = ""
        self.error = ""
        self.suggestion = ""


class BootSequence:
    def __init__(self, title: str = ""):
        self.title = title
        self.steps: list[BootStep] = []

    @contextmanager
    def step(self, name: str):
        step_obj = BootStep(name)
        self.steps.append(step_obj)
        try:
            yield step_obj
        except Exception as exc:  # pragma: no cover - exercised in runtime startup
            step_obj.status = "failed"
            step_obj.error = str(exc)
            raise

    def print_report(self) -> None:
        header = self.title or "Boot sequence"
        print(f"[{header}]")
        for step in self.steps:
            status = step.status.upper()
            print(f"- {step.name}: {status}")
            if step.detail:
                print(f"  {step.detail}")
            if step.error:
                print(f"  error: {step.error}")
            if step.suggestion:
                print(f"  suggestion: {step.suggestion}")

    def ok(self) -> bool:
        return all(step.status == "ok" for step in self.steps)


def read_tail(path: Path | str, n_lines: int = 40) -> str:
    try:
        target = Path(path)
        if not target.exists():
            return ""
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max(1, n_lines):])
    except Exception:
        return ""


__all__ = ["BootStep", "BootSequence", "DiagnosticReport", "build_diagnostic_report", "read_tail"]
