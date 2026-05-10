from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
COMPETITIVE = ROOT / "competitive_analysis"


def run_command(command: list[str]) -> dict[str, object]:
    process = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return {
        "command": " ".join(command),
        "returncode": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def render_benchmark_results(benchmark_runs: list[dict[str, object]]) -> str:
    lines = [
        "# BENCHMARK RESULTS",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Suite Outcomes",
    ]
    for run in benchmark_runs:
        status = "PASS" if run["returncode"] == 0 else "FAIL"
        lines.append(f"- `{run['command']}` -> **{status}**")
    lines.extend(["", "## Raw Outputs"])
    for run in benchmark_runs:
        lines.extend(
            [
                f"### `{run['command']}`",
                "",
                "```text",
                str(run["stdout"]).strip() or "<no stdout>",
                "```",
            ]
        )
        if run["stderr"]:
            lines.extend(["```text", str(run["stderr"]).strip(), "```"])
    return "\n".join(lines) + "\n"


def render_competitor_matrix(benchmark_runs: list[dict[str, object]]) -> str:
    # Evidence-limited matrix: no synthetic claims beyond local benchmark evidence.
    local_pass_rate = sum(1 for run in benchmark_runs if run["returncode"] == 0) / max(len(benchmark_runs), 1)
    return (
        "# COMPETITOR MATRIX\n\n"
        "Generated from repository-local evidence and explicit unknowns.\n\n"
        "## Capability Comparison\n\n"
        "- Jarvis Sovereign V2 candidate: local benchmark pass rate = "
        f"{local_pass_rate:.2%} across coding/cognitive/governance/self-repair suites.\n"
        "- Claude Code: **Unknown in this repository context** (no reproducible local benchmark harness executed here).\n"
        "- Codex CLI: **Unknown in this repository context** (no reproducible local benchmark harness executed here).\n"
        "- OpenDevin: **Unknown in this repository context**.\n"
        "- AutoGPT: **Unknown in this repository context**.\n"
        "- Local agent frameworks: **Unknown in this repository context**.\n"
        "- Mythos standalone: **Not isolated in this run; no separate benchmark execution artifact.**\n"
        "- Friend Jarvis standalone: **Not isolated in this run; no separate benchmark execution artifact.**\n\n"
        "## Truth Constraint\n\n"
        "Any competitor row marked unknown is intentionally left unscored to avoid fabricated superiority claims.\n"
    )


def render_gap_analysis(truth_report: str, benchmark_runs: list[dict[str, object]]) -> str:
    benchmark_failures = [run for run in benchmark_runs if run["returncode"] != 0]
    return (
        "# GAP ANALYSIS\n\n"
        f"- Truth audit findings: {truth_report.count('⚠️')} flagged theater/weakness entries.\n"
        f"- Benchmark suite failures: {len(benchmark_failures)} out of {len(benchmark_runs)} suites.\n"
        "- If any failures remain, classify system as `Architecturally Advanced Prototype — Not Yet Sovereign`.\n"
        "- Sovereign promotion requires all mandatory conditions in the phase prompt to pass with evidence.\n"
    )


def render_autonomy_validation(benchmark_runs: list[dict[str, object]]) -> str:
    passed = all(run["returncode"] == 0 for run in benchmark_runs)
    verdict = "validated" if passed else "not validated"
    return (
        "# AUTONOMY VALIDATION\n\n"
        f"- Autonomous benchmark execution status: **{verdict}**\n"
        "- Evidence source: benchmark pytest suite runs and generated logs.\n"
        "- Continuous scheduler support: `brain/ContinuousCognitionLoop.py` now runs drift scan, provider audits, governance penetration checks, and report writes.\n"
    )


def render_self_repair_validation() -> str:
    return (
        "# SELF-REPAIR VALIDATION\n\n"
        "- `brain/AdaptiveSelfRepair.py` now records repair confidence and executes backup/patch/test/rollback flow.\n"
        "- `brain/MetaCognitionEngine.py` validates patch ids against concrete repair history and scores outcomes.\n"
        "- `benchmarks/self_repair_benchmarks/test_self_repair.py` validates a real failing module patch cycle.\n"
    )


def render_phase6_roadmap(benchmark_runs: list[dict[str, object]]) -> str:
    failed = [run["command"] for run in benchmark_runs if run["returncode"] != 0]
    failure_lines = "\n".join(f"- {entry}" for entry in failed) if failed else "- None"
    return (
        "# PHASE 6 ROADMAP\n\n"
        "## Immediate\n"
        "- Remove duplicate governance module tree (`governance/*` vs `jarvis_os/*`) by selecting one source of truth.\n"
        "- Wire real patch generation model calls into `AutonomousSelfRepairV3` instead of simulation heuristics.\n"
        "- Add competitor harnesses to produce evidence-backed external comparisons.\n\n"
        "## Remaining Failed Gates\n"
        f"{failure_lines}\n"
    )


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    COMPETITIVE.mkdir(parents=True, exist_ok=True)

    audit = run_command([sys.executable, "v3_truth_audit.py"])
    benchmark_runs = [
        run_command([sys.executable, "-m", "pytest", "benchmarks/coding_benchmarks/test_coding_skills.py", "-q"]),
        run_command([sys.executable, "-m", "pytest", "benchmarks/cognitive_benchmarks/test_cognition.py", "-q"]),
        run_command([sys.executable, "-m", "pytest", "benchmarks/governance_benchmarks/test_governance.py", "-q"]),
        run_command([sys.executable, "-m", "pytest", "benchmarks/self_repair_benchmarks/test_self_repair.py", "-q"]),
    ]

    truth_report_path = REPORTS / "SOVEREIGN_TRUTH_REPORT.md"
    truth_report = truth_report_path.read_text(encoding="utf-8") if truth_report_path.exists() else ""
    if audit["returncode"] != 0:
        truth_report = f"# SOVEREIGN TRUTH REPORT - PHASE 5\n\nTruth audit script failed.\n\n```text\n{audit['stderr']}\n```\n"
        write(truth_report_path, truth_report)

    write(REPORTS / "BENCHMARK_RESULTS.md", render_benchmark_results(benchmark_runs))
    matrix = render_competitor_matrix(benchmark_runs)
    write(REPORTS / "COMPETITOR_MATRIX.md", matrix)
    write(COMPETITIVE / "COMPETITOR_MATRIX.md", matrix)
    write(REPORTS / "GAP_ANALYSIS.md", render_gap_analysis(truth_report, benchmark_runs))
    write(REPORTS / "AUTONOMY_VALIDATION.md", render_autonomy_validation(benchmark_runs))
    write(REPORTS / "SELF_REPAIR_VALIDATION.md", render_self_repair_validation())
    write(REPORTS / "PHASE6_ROADMAP.md", render_phase6_roadmap(benchmark_runs))

    status_payload = {"audit": audit, "benchmarks": benchmark_runs}
    write(REPORTS / "phase5_validation_status.json", json.dumps(status_payload, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
