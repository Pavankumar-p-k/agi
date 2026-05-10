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

CANONICAL = {
    "planner": "jarvis_os/core/planner.py",
    "governance": "jarvis_os/RuntimeGovernanceLayer.py",
    "runtime": "jarvis_os/model_runtime_manager.py",
    "memory": "jarvis_os/memory/memory_manager.py",
    "self_repair": "brain/AdaptiveSelfRepair.py",
}

THEATER_TOKENS = ("simulate", "mock-only", "placeholder", "todo", "fixme", "dry run", "print(")


@dataclass
class CmdResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run(cmd: list[str]) -> CmdResult:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return CmdResult(" ".join(cmd), proc.returncode, proc.stdout, proc.stderr)


def _is_wrapper_duplicate(path: Path, canonical_rel: str) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    canonical_name = Path(canonical_rel).stem
    # Handle cases where the canonical name might be aliased or imported differently
    if f"from {canonical_rel.replace('/', '.').replace('.py', '')} import" in text:
        return True
    return False


def _scan_file(path: Path) -> tuple[list[str], list[str]]:
    findings: list[str] = []
    governance: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    for token in THEATER_TOKENS:
        if token in lowered:
            findings.append(f"{path.as_posix()}: contains theater token `{token}`")
            break
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        findings.append(f"{path.as_posix()}: parse error at {exc.lineno}: {exc.msg}")
        return findings, governance
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                findings.append(f"{path.as_posix()}:{node.name} uses pass placeholder")
            lname = node.name.lower()
            if any(k in lname for k in ("validate", "enforce", "audit", "authorize")):
                if not any(isinstance(child, ast.Raise) for child in ast.walk(node)):
                    governance.append(f"{path.as_posix()}:{node.name} validates without raise")
    return findings, governance


def _in_scope(path: Path) -> bool:
    blocked = {"archive", "benchmarks", "tests", "__pycache__", ".venv"}
    return all(part not in blocked for part in path.parts)


def collect() -> dict[str, object]:
    critical_findings: list[str] = []
    governance_findings: list[str] = []
    missing_critical: list[str] = []
    for rel in CRITICAL_PATHS:
        path = ROOT / rel
        if not path.exists():
            missing_critical.append(rel)
            continue
        f, g = _scan_file(path)
        critical_findings.extend(f)
        governance_findings.extend(g)

    duplicates: dict[str, list[str]] = {"planner": [], "governance": [], "runtime": [], "memory": []}
    planners = [p for p in ROOT.rglob("*planner*.py") if _in_scope(p)]
    governance = [p for p in ROOT.rglob("*Governance*.py") if _in_scope(p)]
    runtimes = [p for p in ROOT.rglob("*runtime*manager*.py") if _in_scope(p)]
    memories = [p for p in ROOT.rglob("*memory*.py") if _in_scope(p)]

    for p in planners:
        rel = p.relative_to(ROOT).as_posix()
        if rel != CANONICAL["planner"]:
            if _is_wrapper_duplicate(p, CANONICAL["planner"]):
                continue
            duplicates["planner"].append(rel)
    for p in governance:
        rel = p.relative_to(ROOT).as_posix()
        if rel == CANONICAL["governance"]:
            continue
        if _is_wrapper_duplicate(p, CANONICAL["governance"]) or _is_wrapper_duplicate(p, "governance/GovernanceValidator.py"):
            continue
        # Special case for the benchmark-required GovernanceValidator itself
        if rel == "governance/GovernanceValidator.py":
            continue
        duplicates["governance"].append(rel)
    for p in runtimes:
        rel = p.relative_to(ROOT).as_posix()
        if rel != CANONICAL["runtime"]:
            if _is_wrapper_duplicate(p, CANONICAL["runtime"]):
                continue
            duplicates["runtime"].append(rel)
    for p in memories:
        rel = p.relative_to(ROOT).as_posix()
        if rel != CANONICAL["memory"]:
            if _is_wrapper_duplicate(p, CANONICAL["memory"]):
                continue
            duplicates["memory"].append(rel)

    compile_result = run([sys.executable, "-m", "compileall", "brain", "jarvis_os", "governance", "runtime", "autonomy"])
    bench_result = run([sys.executable, "-m", "pytest", "benchmarks/phase61", "-q"])
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "critical_findings": sorted(set(critical_findings)),
        "weak_governance": sorted(set(governance_findings)),
        "missing_critical": sorted(set(missing_critical)),
        "duplicates": {k: sorted(set(v)) for k, v in duplicates.items()},
        "compileall": compile_result.__dict__,
        "benchmarks": bench_result.__dict__,
    }


def write_reports(audit: dict[str, object]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    duplicate_count = sum(len(v) for v in audit["duplicates"].values())
    critical_count = len(audit["critical_findings"])
    governance_count = len(audit["weak_governance"])
    compile_ok = bool(audit["compileall"]["returncode"] == 0)
    bench_ok = bool(audit["benchmarks"]["returncode"] == 0)
    missing_count = len(audit["missing_critical"])

    (REPORTS / "PHASE61_TRUTH_AUDIT.md").write_text(
        "\n".join(
            [
                "# PHASE61 TRUTH AUDIT",
                "",
                f"Generated: {audit['generated']}",
                "",
                "## Critical Path Theater Findings",
                *([f"- {x}" for x in audit["critical_findings"]] or ["- None"]),
                "",
                "## Weak Governance Findings",
                *([f"- {x}" for x in audit["weak_governance"]] or ["- None"]),
                "",
                "## Missing Critical Files",
                *([f"- {x}" for x in audit["missing_critical"]] or ["- None"]),
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (REPORTS / "DUPLICATE_COLLAPSE_REPORT.md").write_text(
        "\n".join(
            [
                "# DUPLICATE COLLAPSE REPORT",
                "",
                f"- duplicate authority entries: {duplicate_count}",
                "",
                "## Duplicates by authority",
                f"- planner: {len(audit['duplicates']['planner'])}",
                f"- governance: {len(audit['duplicates']['governance'])}",
                f"- runtime: {len(audit['duplicates']['runtime'])}",
                f"- memory: {len(audit['duplicates']['memory'])}",
                "",
                "## Duplicate files",
                *([f"- {x}" for k in ("planner", "governance", "runtime", "memory") for x in audit["duplicates"][k]] or ["- None"]),
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (REPORTS / "GOVERNANCE_ABSOLUTISM_REPORT.md").write_text(
        "\n".join(
            [
                "# GOVERNANCE ABSOLUTISM REPORT",
                "",
                f"- weak governance findings: {governance_count}",
                "",
                "## Details",
                *([f"- {x}" for x in audit["weak_governance"]] or ["- None"]),
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (REPORTS / "AUTONOMY_REALITY_REPORT.md").write_text(
        "\n".join(
            [
                "# AUTONOMY REALITY REPORT",
                "",
                f"- critical theater findings: {critical_count}",
                f"- missing critical files: {missing_count}",
                "",
                "## Blocking items",
                *([f"- {x}" for x in audit["critical_findings"]] or ["- None"]),
                *([f"- missing: {x}" for x in audit["missing_critical"]] or []),
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (REPORTS / "BENCHMARK_PHASE61.md").write_text(
        "\n".join(
            [
                "# BENCHMARK PHASE61",
                "",
                f"- compileall: {'PASS' if compile_ok else 'FAIL'}",
                f"- benchmarks/phase61: {'PASS' if bench_ok else 'FAIL'}",
                "",
                "## Commands",
                f"- `{audit['compileall']['command']}`",
                f"- `{audit['benchmarks']['command']}`",
                "",
                "## Raw Output",
                "```text",
                f"{audit['compileall']['stdout']}{audit['compileall']['stderr']}",
                f"{audit['benchmarks']['stdout']}{audit['benchmarks']['stderr']}",
                "```",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    candidate = all(
        [
            critical_count == 0,
            governance_count == 0,
            duplicate_count == 0,
            compile_ok,
            bench_ok,
            missing_count == 0,
        ]
    )
    classification = "Sovereign Candidate" if candidate else "Advanced Prototype"
    (REPORTS / "FINAL_SOVEREIGN_CANDIDATE.md").write_text(
        "\n".join(
            [
                "# FINAL SOVEREIGN CANDIDATE",
                "",
                f"- classification: **{classification}**",
                f"- critical theater findings: {critical_count}",
                f"- weak governance findings: {governance_count}",
                f"- duplicate authority findings: {duplicate_count}",
                f"- missing critical files: {missing_count}",
                f"- compileall pass: {compile_ok}",
                f"- benchmark pass: {bench_ok}",
                "",
                "- gate rule: candidate requires all counts at 0 and all checks pass.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (REPORTS / "phase61_validation_status.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")


def main() -> int:
    audit = collect()
    write_reports(audit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
