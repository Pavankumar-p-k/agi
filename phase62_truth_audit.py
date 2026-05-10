from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"

CANONICAL = {
    "planner": "jarvis_os/core/planner.py",
    "governance": "jarvis_os/RuntimeGovernanceLayer.py",
    "runtime": "jarvis_os/model_runtime_manager.py",
    "memory": "jarvis_os/memory/memory_manager.py",
    "self_repair": "brain/AdaptiveSelfRepair.py",
    "executor": "jarvis_os/core/executor.py",
    "loop": "jarvis_os/core/loop.py",
}

REQUIRED_FILES = [
    "autonomy/l3_executor/executor_engine.py",
    "autonomy/l3_executor/executor_layer.py",
    "brain/ContinuousCognitionLoop.py",
    "brain/CounterfactualSimulator.py",
    "brain/adapters.py",
    "jarvis_os/ProviderSimulationEngine.py",
]

CRITICAL_PATHS = [
    "autonomy/api/autonomous_routes.py",
    "autonomy/core/autonomous_orchestrator.py",
    "autonomy/l3_executor/executor_engine.py",
    "autonomy/l3_executor/executor_layer.py",
    "brain/ContinuousCognitionLoop.py",
    "brain/CounterfactualSimulator.py",
    "brain/UnifiedBrain.py",
    "brain/adapters.py",
    "governance/GovernanceValidator.py",
    "jarvis_os/ProviderSimulationEngine.py",
    "jarvis_os/core/executor.py",
    "jarvis_os/core/loop.py",
    "jarvis_os/model_runtime_manager.py",
    "jarvis_os/tools/coding_tools.py",
]

THEATER_TOKENS = ("todo", "fixme", "notimplemented", "placeholder", "dry run")


@dataclass
class Cmd:
    command: str
    returncode: int
    stdout: str
    stderr: str


def run(command: list[str]) -> Cmd:
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return Cmd(" ".join(command), proc.returncode, proc.stdout, proc.stderr)


def is_reexport_or_adapter(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    if lines and all(line.startswith("from ") or line.startswith("__all__") for line in lines):
        return True
    return "adapter" in text.lower()


def scan_file(path: Path) -> tuple[list[str], list[str]]:
    findings: list[str] = []
    weak: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    if any(token in lowered for token in THEATER_TOKENS):
        findings.append(path.relative_to(ROOT).as_posix())
    try:
        tree = ast.parse(text)
    except SyntaxError:
        findings.append(path.relative_to(ROOT).as_posix())
        return findings, weak
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lname = node.name.lower()
            if any(k in lname for k in ("validate", "audit", "enforce", "authorize")):
                if not any(isinstance(child, ast.Raise) for child in ast.walk(node)):
                    weak.append(f"{path.relative_to(ROOT).as_posix()}:{node.name}")
    return findings, weak


def duplicate_authorities() -> list[str]:
    class_owner = {
        "PlanningEngine": CANONICAL["planner"],
        "RuntimeGovernanceLayer": CANONICAL["governance"],
        "ModelRuntimeManager": CANONICAL["runtime"],
        "MemoryManager": CANONICAL["memory"],
        "ExecutionEngine": CANONICAL["executor"],
        "AgentLoop": CANONICAL["loop"],
    }
    duplicates: list[str] = []
    for path in ROOT.rglob("*.py"):
        if any(part in {"archive", "benchmarks", "tests", "__pycache__", ".venv"} for part in path.parts):
            continue
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            owner = class_owner.get(node.name)
            if owner and owner != rel:
                duplicates.append(f"{rel}:{node.name}")
    return sorted(set(duplicates))


def missing_required() -> list[str]:
    return [path for path in REQUIRED_FILES if not (ROOT / path).exists()]


def audit() -> dict[str, object]:
    theater: list[str] = []
    weak: list[str] = []
    missing_critical: list[str] = []
    for rel in CRITICAL_PATHS:
        path = ROOT / rel
        if not path.exists():
            missing_critical.append(rel)
            continue
        t, w = scan_file(path)
        theater.extend(t)
        weak.extend(w)
    compile_result = run([sys.executable, "-m", "compileall", "brain", "jarvis_os", "governance", "runtime", "autonomy"])
    phase61_result = run([sys.executable, "-m", "pytest", "benchmarks/phase61", "-q"])
    phase62_result = run([sys.executable, "-m", "pytest", "benchmarks/phase62", "-q"])
    duplicates = duplicate_authorities()
    missing = missing_required()
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "duplicate_authority": duplicates,
        "missing_files": missing,
        "critical_theater": sorted(set(theater)),
        "weak_governance": sorted(set(weak)),
        "missing_critical": sorted(set(missing_critical)),
        "compileall": compile_result.__dict__,
        "phase61_bench": phase61_result.__dict__,
        "phase62_bench": phase62_result.__dict__,
    }


def write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def write_reports(data: dict[str, object]) -> None:
    dup_count = len(data["duplicate_authority"])
    missing_count = len(data["missing_files"])
    theater_count = len(data["critical_theater"])
    governance_count = len(data["weak_governance"])
    compile_ok = data["compileall"]["returncode"] == 0
    bench_ok = data["phase61_bench"]["returncode"] == 0 and data["phase62_bench"]["returncode"] == 0
    candidate = all(
        [
            dup_count == 0,
            missing_count == 0,
            theater_count == 0,
            governance_count == 0,
            compile_ok,
            bench_ok,
            len(data["missing_critical"]) == 0,
        ]
    )
    classification = "Sovereign Candidate" if candidate else "Advanced Prototype"

    write(
        REPORTS / "PHASE62_TRUTH_AUDIT.md",
        "\n".join(
            [
                "# PHASE62 TRUTH AUDIT",
                "",
                f"Generated: {data['generated']}",
                f"- duplicate authority: {dup_count}",
                f"- missing files: {missing_count}",
                f"- critical theater: {theater_count}",
                f"- weak governance: {governance_count}",
                "",
                "## Duplicate Authority Files",
                *([f"- {x}" for x in data["duplicate_authority"]] or ["- None"]),
                "",
                "## Missing Required Files",
                *([f"- {x}" for x in data["missing_files"]] or ["- None"]),
                "",
            ]
        )
        + "\n",
    )

    write(
        REPORTS / "AUTHORITY_COLLAPSE_FINAL.md",
        "\n".join(
            [
                "# AUTHORITY COLLAPSE FINAL",
                "",
                f"- duplicate authority count: {dup_count}",
                "## Canonical Ownership",
                *[f"- {k}: `{v}`" for k, v in CANONICAL.items()],
                "",
                "## Remaining Duplicates",
                *([f"- {x}" for x in data["duplicate_authority"]] or ["- None"]),
                "",
            ]
        )
        + "\n",
    )

    write(
        REPORTS / "MISSING_FILES_RESOLUTION.md",
        "\n".join(
            [
                "# MISSING FILES RESOLUTION",
                "",
                f"- missing required files: {missing_count}",
                "## Required Files",
                *[f"- {x}" for x in REQUIRED_FILES],
                "",
                "## Missing After Resolution",
                *([f"- {x}" for x in data["missing_files"]] or ["- None"]),
                "",
            ]
        )
        + "\n",
    )

    write(
        REPORTS / "EXECUTION_PATH_VALIDATION.md",
        "\n".join(
            [
                "# EXECUTION PATH VALIDATION",
                "",
                "- user input -> planner -> governance -> runtime -> executor -> memory -> self-repair",
                f"- duplicate authority count: {dup_count}",
                f"- weak governance count: {governance_count}",
                "",
                "## Missing Critical Modules",
                *([f"- {x}" for x in data["missing_critical"]] or ["- None"]),
                "",
            ]
        )
        + "\n",
    )

    write(
        REPORTS / "BENCHMARK_PHASE62.md",
        "\n".join(
            [
                "# BENCHMARK PHASE62",
                "",
                f"- compileall: {'PASS' if compile_ok else 'FAIL'}",
                f"- phase61 benchmarks: {'PASS' if data['phase61_bench']['returncode'] == 0 else 'FAIL'}",
                f"- phase62 benchmarks: {'PASS' if data['phase62_bench']['returncode'] == 0 else 'FAIL'}",
                "",
                "## Commands",
                f"- `{data['compileall']['command']}`",
                f"- `{data['phase61_bench']['command']}`",
                f"- `{data['phase62_bench']['command']}`",
                "",
                "## Raw Output",
                "```text",
                f"{data['compileall']['stdout']}{data['compileall']['stderr']}",
                f"{data['phase61_bench']['stdout']}{data['phase61_bench']['stderr']}",
                f"{data['phase62_bench']['stdout']}{data['phase62_bench']['stderr']}",
                "```",
                "",
            ]
        )
        + "\n",
    )

    write(
        REPORTS / "SOVEREIGN_CANDIDATE_FINAL.md",
        "\n".join(
            [
                "# SOVEREIGN CANDIDATE FINAL",
                "",
                f"- classification: **{classification}**",
                f"- duplicate authority: {dup_count}",
                f"- missing files: {missing_count}",
                f"- critical theater: {theater_count}",
                f"- weak governance: {governance_count}",
                f"- compileall pass: {compile_ok}",
                f"- benchmarks pass: {bench_ok}",
                "",
                "- rule: Sovereign Candidate requires all counts = 0 and all gates pass.",
                "",
            ]
        )
        + "\n",
    )

    write(REPORTS / "phase62_validation_status.json", json.dumps(data, indent=2) + "\n")


def main() -> int:
    data = audit()
    write_reports(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
