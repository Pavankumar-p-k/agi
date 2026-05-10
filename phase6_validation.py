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

TARGET_DIRS = [
    "jarvis",
    "jarvis_os",
    "brain",
    "mythos",
    "friend_jarvis",
    "runtime",
    "governance",
    "autonomy",
]

THEATER_TOKENS = ("todo", "notimplemented", "simulate", "dry run", "placeholder")
SENSITIVE_TOKENS = ("finance", "medical", "legal", "identity", "credential", "root", "offline")


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run(command: list[str]) -> CommandResult:
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    return CommandResult(" ".join(command), proc.returncode, proc.stdout, proc.stderr)


def scoped_roots() -> list[Path]:
    roots: list[Path] = []
    for name in TARGET_DIRS:
        candidate = ROOT / name
        if candidate.exists() and candidate.is_dir():
            roots.append(candidate)
    return roots


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in scoped_roots():
        files.extend(
            path
            for path in root.rglob("*.py")
            if ".venv" not in path.parts and "__pycache__" not in path.parts
        )
    return files


def truth_scan() -> dict[str, object]:
    theater: list[str] = []
    weak_governance: list[str] = []
    parse_errors: list[str] = []
    duplicate_groups: dict[str, list[str]] = {
        "governance_layers": [],
        "planners": [],
        "runtime_managers": [],
        "memory_cores": [],
        "orchestrators": [],
        "self_repair": [],
    }

    files = iter_python_files()
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            tree = ast.parse(text)
        except SyntaxError as exc:
            parse_errors.append(f"{rel}:{exc.lineno}:{exc.msg}")
            continue

        lowered = text.lower()
        if any(token in lowered for token in THEATER_TOKENS):
            theater.append(f"{rel}: contains theater token")

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name.lower()
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    theater.append(f"{rel}:{node.name} uses pass placeholder")
                if ("validate" in name or "audit" in name or "enforce" in name) and not any(
                    isinstance(child, ast.Raise) for child in ast.walk(node)
                ):
                    weak_governance.append(f"{rel}:{node.name} has no hard raise path")

        rel_lower = rel.lower()
        if "runtimegovernancelayer.py" in rel_lower:
            duplicate_groups["governance_layers"].append(rel)
        if "planner" in rel_lower and rel_lower.endswith(".py"):
            duplicate_groups["planners"].append(rel)
        if "runtime" in rel_lower and "manager" in rel_lower and rel_lower.endswith(".py"):
            duplicate_groups["runtime_managers"].append(rel)
        if "memory" in rel_lower and rel_lower.endswith(".py"):
            duplicate_groups["memory_cores"].append(rel)
        if "orchestrator" in rel_lower and rel_lower.endswith(".py"):
            duplicate_groups["orchestrators"].append(rel)
        if "repair" in rel_lower and rel_lower.endswith(".py"):
            duplicate_groups["self_repair"].append(rel)

    return {
        "scoped_roots": [path.relative_to(ROOT).as_posix() for path in scoped_roots()],
        "files_scanned": len(files),
        "theater": sorted(set(theater)),
        "weak_governance": sorted(set(weak_governance)),
        "parse_errors": parse_errors,
        "duplicate_groups": duplicate_groups,
    }


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def render_truth(audit: dict[str, object]) -> str:
    lines = [
        "# PHASE6 TRUTH AUDIT",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Scope",
    ]
    for root in audit["scoped_roots"]:
        lines.append(f"- `{root}`")
    lines.extend(
        [
            "",
            f"Files scanned: `{audit['files_scanned']}`",
            "",
            "## Theater Findings",
        ]
    )
    if audit["theater"]:
        lines.extend(f"- {entry}" for entry in audit["theater"])
    else:
        lines.append("- None")
    lines.extend(["", "## Weak Governance Findings"])
    if audit["weak_governance"]:
        lines.extend(f"- {entry}" for entry in audit["weak_governance"])
    else:
        lines.append("- None")
    lines.extend(["", "## Parse Errors"])
    if audit["parse_errors"]:
        lines.extend(f"- {entry}" for entry in audit["parse_errors"])
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def render_collapse_map(audit: dict[str, object]) -> str:
    dup = audit["duplicate_groups"]
    return (
        "# ARCHITECTURE COLLAPSE MAP\n\n"
        "## Canonical Ownership\n"
        "- planner: `jarvis_os/core/planner.py`\n"
        "- governance layer: `jarvis_os/RuntimeGovernanceLayer.py`\n"
        "- runtime manager: `jarvis_os/model_runtime_manager.py`\n"
        "- self-repair engine: `brain/AdaptiveSelfRepair.py`\n"
        "- continuous cognition loop: `brain/ContinuousCognitionLoop.py`\n"
        "- memory authority: `jarvis_os/memory/memory_manager.py`\n\n"
        "## Duplicate Clusters\n"
        f"- governance_layers: {len(dup['governance_layers'])}\n"
        f"- planners: {len(dup['planners'])}\n"
        f"- runtime_managers: {len(dup['runtime_managers'])}\n"
        f"- memory_cores: {len(dup['memory_cores'])}\n"
        f"- orchestrators: {len(dup['orchestrators'])}\n"
        f"- self_repair: {len(dup['self_repair'])}\n"
    )


def render_benchmark_phase6(compile_result: CommandResult, bench_result: CommandResult) -> str:
    return (
        "# BENCHMARK PHASE6\n\n"
        f"- compileall: {'PASS' if compile_result.ok else 'FAIL'}\n"
        f"- phase6 benchmark suite: {'PASS' if bench_result.ok else 'FAIL'}\n\n"
        "## Commands\n"
        f"- `{compile_result.command}`\n"
        f"- `{bench_result.command}`\n\n"
        "## Raw Output\n"
        "```text\n"
        f"{compile_result.stdout}{compile_result.stderr}\n"
        f"{bench_result.stdout}{bench_result.stderr}\n"
        "```\n"
    )


def render_competitor_matrix_phase6(bench_ok: bool) -> str:
    status = "validated locally" if bench_ok else "failed local benchmark gates"
    return (
        "# COMPETITOR MATRIX PHASE6\n\n"
        "- Jarvis Sovereign candidate: "
        + status
        + "\n"
        "- Claude Code: unknown in this repo run (no side-by-side local harness)\n"
        "- Codex CLI: unknown in this repo run (no side-by-side local harness)\n"
        "- AutoGPT: unknown in this repo run\n"
        "- OpenDevin: unknown in this repo run\n"
        "- Manus: unknown in this repo run\n"
        "- Mythos standalone: unavailable in current directory map\n"
        "- Friend Jarvis standalone: unavailable in current directory map\n"
    )


def render_gap_eradication(audit: dict[str, object], compile_result: CommandResult, bench_result: CommandResult) -> str:
    return (
        "# GAP ERADICATION REPORT\n\n"
        f"- theater findings: {len(audit['theater'])}\n"
        f"- weak governance findings: {len(audit['weak_governance'])}\n"
        f"- parse errors: {len(audit['parse_errors'])}\n"
        f"- compileall pass: {compile_result.ok}\n"
        f"- benchmark pass: {bench_result.ok}\n"
    )


def render_final_classification(audit: dict[str, object], compile_result: CommandResult, bench_result: CommandResult) -> str:
    no_placeholders = len(audit["theater"]) == 0
    hard_governance = len(audit["weak_governance"]) == 0
    runnable = compile_result.ok and bench_result.ok
    if no_placeholders and hard_governance and runnable:
        classification = "Sovereign Cognitive OS"
    elif runnable:
        classification = "Advanced Prototype"
    else:
        classification = "Experimental Fusion System"
    return (
        "# FINAL SOVEREIGN CLASSIFICATION\n\n"
        f"- classification: **{classification}**\n"
        f"- no placeholder critical functions: {no_placeholders}\n"
        f"- hard governance exception coverage: {hard_governance}\n"
        f"- compileall pass: {compile_result.ok}\n"
        f"- benchmark pass: {bench_result.ok}\n"
        "- mandatory gate rule: sovereignty requires all critical gates true.\n"
    )


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    audit = truth_scan()
    compile_result = run([sys.executable, "-m", "compileall", "brain", "jarvis_os", "governance", "runtime", "autonomy"])
    bench_result = run([sys.executable, "-m", "pytest", "benchmarks/phase6", "-q"])

    write(REPORTS / "PHASE6_TRUTH_AUDIT.md", render_truth(audit))
    write(REPORTS / "ARCHITECTURE_COLLAPSE_MAP.md", render_collapse_map(audit))
    write(REPORTS / "BENCHMARK_PHASE6.md", render_benchmark_phase6(compile_result, bench_result))
    write(REPORTS / "COMPETITOR_MATRIX_PHASE6.md", render_competitor_matrix_phase6(bench_result.ok))
    write(REPORTS / "GAP_ERADICATION_REPORT.md", render_gap_eradication(audit, compile_result, bench_result))
    write(REPORTS / "FINAL_SOVEREIGN_CLASSIFICATION.md", render_final_classification(audit, compile_result, bench_result))
    write(
        REPORTS / "phase6_validation_status.json",
        json.dumps(
            {
                "audit": audit,
                "compileall": compile_result.__dict__,
                "benchmarks": bench_result.__dict__,
            },
            indent=2,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

