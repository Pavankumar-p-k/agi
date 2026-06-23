"""scripts/benchmark_android.py

Runs 6 Android app benchmarks through the full autonomous build pipeline.
Collects detailed metrics from CompilerRepairEngine, PatternFailureMemory,
runtime validation, and APK generation.

Usage:
    python scripts/benchmark_android.py [--benchmarks 1,2,3,4,5,6] [--output reports/android_benchmark_report.json]
"""
import sys
import os
import json
import asyncio
import time
import tempfile
import shutil
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["CHAT_MODEL"] = os.environ.get("CHAT_MODEL", "ollama/llama3.1:8b")
os.environ["CODE_MODEL"] = os.environ.get("CODE_MODEL", "ollama/qwen2.5-coder:3b")

from brain.UnifiedBrain import UnifiedBrain
from brain.goals import GoalStatus

BENCHMARKS = {
    1: {
        "name": "Calculator App",
        "goal": """Build a simple Android calculator app with Java:
- Material 3 design
- Basic operations: +, -, *, /
- Number input with buttons 0-9
- Clear (C) button
- Display showing input and result
- Landscape support
- Unit tests with JUnit 4""",
    },
    2: {
        "name": "Notes App",
        "goal": """Build a note-taking Android app with Java:
- Material 3 design
- RecyclerView for note list
- Create, edit, delete notes
- Room database (Entity, DAO, Database)
- ViewModel + LiveData
- Search notes by title
- Dark mode support""",
    },
    3: {
        "name": "Todo App",
        "goal": """Build a todo list Android app with Java:
- Material 3 design
- RecyclerView for todo items
- Add/complete/delete todos
- Room database (Entity, DAO, Database)
- ViewModel + LiveData
- Sort by priority
- Mark items as done with strikethrough""",
    },
    4: {
        "name": "Expense Tracker",
        "goal": """Build an expense tracker Android app with Java:
- Material 3 design
- Add expenses with amount, category, date, description
- RecyclerView showing all expenses
- Room database (Entity, DAO, Database)
- ViewModel + LiveData
- Total expense summary
- Filter by category""",
    },
    5: {
        "name": "Weather App",
        "goal": """Build a weather Android app with Java:
- Material 3 design
- Show current weather (temperature, conditions, humidity)
- 5-day forecast RecyclerView
- Search by city name
- Use mock data (no real API key needed)
- ViewModel + LiveData
- Pull-to-refresh""",
    },
    6: {
        "name": "Chat App",
        "goal": """Build a simple chat Android app with Java:
- Material 3 design
- RecyclerView for message list
- Send message via text input
- Messages show sender, timestamp, content
- Room database (Entity, DAO, Database)
- ViewModel + LiveData
- Auto-scroll to latest message""",
    },
}


def _extract_build_metrics(brain: UnifiedBrain) -> dict:
    """Extract build metrics from the AutomationLoop and CompilerRepairEngine."""
    auto = brain.automation
    metrics = {}

    metrics["repair_cycles"] = auto._last_build_metrics.get("repair_cycles", 0)
    metrics["repaired_errors"] = auto._last_build_metrics.get("repaired_errors", 0)
    metrics["unresolved_errors"] = auto._last_build_metrics.get("unresolved_errors", 0)
    metrics["memory_hits"] = auto._last_build_metrics.get("memory_hits", 0)
    metrics["build_success"] = auto._last_build_metrics.get("build_success", False)
    metrics["fix_rate_pct"] = auto._last_build_metrics.get("fix_rate_pct", 0)
    metrics["total_errors"] = auto._last_build_metrics.get("total_errors", 0)

    # PatternFailureMemory stats
    try:
        pfm = auto._pattern_memory
        if pfm:
            pfm_stats = pfm.get_stats()
            metrics["pattern_memory_total"] = pfm_stats.get("total_patterns", 0)
            metrics["pattern_memory_fixes"] = pfm_stats.get("total_fixes_applied", 0)
    except Exception:
        pass

    # Legacy FailureMemory stats
    metrics["failure_memory_size"] = len(auto.failure_memory._exact) + len(auto.failure_memory._patterns)
    metrics["pattern_generalizations"] = auto.failure_memory._generalization_count

    return metrics


def _collect_files(workdir: str) -> list[dict]:
    """Collect generated files with sizes."""
    files = []
    base = os.path.abspath(workdir)
    for root, _dirs, fnames in os.walk(base):
        for f in fnames:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, base)
            if not rel.startswith("brain") and not rel.startswith(".") and not rel.startswith("data"):
                try:
                    files.append({"path": rel, "size": os.path.getsize(full)})
                except Exception:
                    files.append({"path": rel, "size": 0})
    return sorted(files, key=lambda x: x["path"])


def _find_apk(workdir: str) -> str:
    """Find the generated APK file."""
    for root, _dirs, files in os.walk(workdir):
        for f in files:
            if f.endswith(".apk") and "debug" in f:
                return os.path.join(root, f)
    return ""


def _check_runtime_access() -> bool:
    """Check if ADB and emulator are available for runtime validation."""
    adb = shutil.which("adb") or shutil.which("adb.exe")
    emulator = shutil.which("emulator") or shutil.which("emulator.exe")
    return bool(adb) and bool(emulator)


async def run_benchmark(bench_id: int, bench: dict) -> dict:
    """Run a single benchmark and return results."""
    name = bench["name"]
    goal = bench["goal"]

    print(f"\n{'='*70}")
    print(f"BENCHMARK {bench_id}: {name}")
    print(f"{'='*70}")
    print(f"Model: chat={os.environ.get('CHAT_MODEL')} code={os.environ.get('CODE_MODEL')}")

    workdir = os.path.join(tempfile.gettempdir(), f"jarvis_bench_{bench_id}")
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    os.makedirs(workdir)

    print(f"Workdir: {workdir}")
    start_time = time.time()

    brain = UnifiedBrain(workdir)
    brain.automation.MAX_REPAIR_ATTEMPTS = 8

    goal_obj = await brain.create_goal(goal, priority=10)
    print(f"Goal ID: {goal_obj.id[:16]}...")

    result = await brain.automation.run_once(goal_obj)
    elapsed = time.time() - start_time

    g = brain.goals.get(goal_obj.id)
    status = g.status.value if g else "unknown"
    goal_result = (g.result or "")[:200] if g else ""

    # Collect metrics
    build_metrics = _extract_build_metrics(brain)
    files = _collect_files(workdir)
    apk_path = _find_apk(workdir)

    # Check for APK
    apk_generated = bool(apk_path)
    apk_size = os.path.getsize(apk_path) if apk_path else 0

    # Runtime validation check
    runtime_validation = False
    if build_metrics.get("build_success") and _check_runtime_access():
        try:
            runtime_ok = await brain.automation._phase_runtime_validation(
                goal, workdir, {"project_name": name.lower().replace(" ", "_")}, goal_obj.id
            )
            runtime_validation = runtime_ok
        except Exception as e:
            print(f"  Runtime validation error: {e}")

    metrics = {
        "benchmark_id": bench_id,
        "benchmark_name": name,
        "build_success": build_metrics.get("build_success", False),
        "test_success": False,  # Checked below
        "apk_generated": apk_generated,
        "apk_size_bytes": apk_size,
        "repair_cycles": build_metrics.get("repair_cycles", 0),
        "repaired_errors": build_metrics.get("repaired_errors", 0),
        "unresolved_errors": build_metrics.get("unresolved_errors", 0),
        "pattern_memory_hits": build_metrics.get("memory_hits", 0),
        "pattern_memory_total": build_metrics.get("pattern_memory_total", 0),
        "fix_rate_pct": build_metrics.get("fix_rate_pct", 0),
        "total_errors": build_metrics.get("total_errors", 0),
        "failure_memory_size": build_metrics.get("failure_memory_size", 0),
        "pattern_generalizations": build_metrics.get("pattern_generalizations", 0),
        "runtime_validation": runtime_validation,
        "files_generated": len(files),
        "completion_time_s": round(elapsed, 1),
        "goal_status": status,
        "goal_result": goal_result,
    }

    # Check for test success from memory traces
    traces = brain.memory.task.get_recent(limit=500) if hasattr(brain.memory, "task") else []
    test_pass = any(
        "test" in t.get("action_name", "") and t.get("success")
        for t in traces
    )
    metrics["test_success"] = test_pass

    print(f"\n  Results:")
    for k, v in metrics.items():
        if k != "goal_result":
            print(f"    {k}: {v}")

    return metrics


async def main():
    parser = argparse.ArgumentParser(description="Android benchmark suite")
    parser.add_argument("--benchmarks", type=str, default="1,2,3,4,5,6",
                        help="Comma-separated list of benchmark IDs to run (default: all)")
    parser.add_argument("--output", type=str, default="reports/android_benchmark_report.json",
                        help="Output JSON path")
    parser.add_argument("--md", type=str, default="reports/android_benchmark_report.md",
                        help="Output Markdown report path")
    args = parser.parse_args()

    bench_ids = [int(b.strip()) for b in args.benchmarks.split(",")]
    bench_ids = [b for b in bench_ids if b in BENCHMARKS]

    if not bench_ids:
        print("No valid benchmarks selected. Available: 1-6")
        sys.exit(1)

    print(f"Selected benchmarks: {[BENCHMARKS[b]['name'] for b in bench_ids]}")
    print(f"Output JSON: {args.output}")

    all_results = []
    suite_start = time.time()

    for bid in bench_ids:
        try:
            result = await run_benchmark(bid, BENCHMARKS[bid])
            all_results.append(result)
        except Exception as e:
            print(f"Benchmark {bid} failed with error: {e}")
            import traceback
            traceback.print_exc()
            all_results.append({
                "benchmark_id": bid,
                "benchmark_name": BENCHMARKS[bid]["name"],
                "build_success": False,
                "error": str(e),
            })

    suite_elapsed = time.time() - suite_start

    # Calculate aggregate
    total = len(all_results)
    successes = sum(1 for r in all_results if r.get("build_success"))
    apks = sum(1 for r in all_results if r.get("apk_generated"))
    tests_pass = sum(1 for r in all_results if r.get("test_success"))
    runtime_pass = sum(1 for r in all_results if r.get("runtime_validation"))
    total_repairs = sum(r.get("repair_cycles", 0) for r in all_results)
    total_errors = sum(r.get("total_errors", 0) for r in all_results)
    total_fixed = sum(r.get("repaired_errors", 0) for r in all_results)
    total_memory_hits = sum(r.get("pattern_memory_hits", 0) for r in all_results)

    aggregate = {
        "total_benchmarks": total,
        "build_successful": successes,
        "build_success_rate_pct": round(successes / total * 100, 1) if total else 0,
        "apk_generated": apks,
        "apk_generation_rate_pct": round(apks / total * 100, 1) if total else 0,
        "tests_passed": tests_pass,
        "runtime_validations_passed": runtime_pass,
        "total_repair_cycles": total_repairs,
        "total_errors_encountered": total_errors,
        "total_errors_repaired": total_fixed,
        "total_memory_hits": total_memory_hits,
        "overall_fix_rate_pct": round(total_fixed / max(total_errors, 1) * 100, 1),
        "suite_completion_time_s": round(suite_elapsed, 1),
        "timestamp": datetime.now().isoformat(),
    }

    report = {
        "summary": aggregate,
        "benchmarks": all_results,
        "config": {
            "chat_model": os.environ.get("CHAT_MODEL"),
            "code_model": os.environ.get("CODE_MODEL"),
            "max_repair_attempts": 8,
        },
    }

    # Write JSON
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nJSON report saved: {args.output}")

    # Write Markdown
    md_path = args.md
    os.makedirs(os.path.dirname(md_path) or ".", exist_ok=True)
    _write_markdown_report(md_path, report)
    print(f"Markdown report saved: {md_path}")

    # Print summary
    print(f"\n{'='*70}")
    print("SUITE SUMMARY")
    print(f"{'='*70}")
    print(f"  Benchmarks:     {successes}/{total} passed ({aggregate['build_success_rate_pct']}%)")
    print(f"  APKs generated: {apks}/{total} ({aggregate['apk_generation_rate_pct']}%)")
    print(f"  Tests passed:   {tests_pass}/{total}")
    print(f"  Runtime valid:  {runtime_pass}/{total}")
    print(f"  Repair cycles:  {total_repairs}")
    print(f"  Errors fixed:   {total_fixed}/{total_errors} ({aggregate['overall_fix_rate_pct']}%)")
    print(f"  Memory hits:    {total_memory_hits}")
    print(f"  Suite time:     {suite_elapsed:.1f}s")
    print(f"{'='*70}")


def _write_markdown_report(path: str, report: dict):
    """Generate a readable Markdown report from benchmark data."""
    summary = report.get("summary", {})
    benchmarks = report.get("benchmarks", [])
    config = report.get("config", {})

    lines = [
        "# Android Benchmark Report",
        "",
        f"**Generated**: {summary.get('timestamp', 'unknown')}",
        f"**Chat Model**: {config.get('chat_model', 'default')}",
        f"**Code Model**: {config.get('code_model', 'default')}",
        f"**Max Repair Attempts**: {config.get('max_repair_attempts', 8)}",
        "",
        "## Suite Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Benchmarks | {summary.get('total_benchmarks', 0)} |",
        f"| Build Success | {summary.get('build_successful', 0)}/{summary.get('total_benchmarks', 0)} ({summary.get('build_success_rate_pct', 0)}%) |",
        f"| APK Generated | {summary.get('apk_generated', 0)}/{summary.get('total_benchmarks', 0)} ({summary.get('apk_generation_rate_pct', 0)}%) |",
        f"| Tests Passed | {summary.get('tests_passed', 0)}/{summary.get('total_benchmarks', 0)} |",
        f"| Runtime Validations | {summary.get('runtime_validations_passed', 0)}/{summary.get('total_benchmarks', 0)} |",
        f"| Total Repair Cycles | {summary.get('total_repair_cycles', 0)} |",
        f"| Total Errors | {summary.get('total_errors_encountered', 0)} |",
        f"| Total Errors Repaired | {summary.get('total_errors_repaired', 0)} |",
        f"| Overall Fix Rate | {summary.get('overall_fix_rate_pct', 0)}% |",
        f"| Total Memory Hits | {summary.get('total_memory_hits', 0)} |",
        f"| Suite Completion Time | {summary.get('suite_completion_time_s', 0)}s |",
        "",
        "## Per-Benchmark Results",
        "",
        "| # | Name | Build | APK | Tests | Runtime | Repair Cycles | Errors | Fixed | Fix Rate | Memory Hits | Time (s) |",
        "|---|------|-------|-----|-------|---------|---------------|--------|-------|----------|-------------|----------|",
    ]

    for b in benchmarks:
        lines.append(
            f"| {b.get('benchmark_id', '?')} "
            f"| {b.get('benchmark_name', '?')[:25]} "
            f"| {'PASS' if b.get('build_success') else 'FAIL'} "
            f"| {'YES' if b.get('apk_generated') else 'NO'} "
            f"| {'PASS' if b.get('test_success') else 'FAIL'} "
            f"| {'PASS' if b.get('runtime_validation') else 'SKIP'} "
            f"| {b.get('repair_cycles', 0)} "
            f"| {b.get('total_errors', 0)} "
            f"| {b.get('repaired_errors', 0)} "
            f"| {b.get('fix_rate_pct', 0)}% "
            f"| {b.get('pattern_memory_hits', 0)} "
            f"| {b.get('completion_time_s', 0)}s |"
        )

    lines.extend([
        "",
        "## Detailed Results",
        "",
    ])

    for b in benchmarks:
        lines.extend([
            f"### {b.get('benchmark_id', '?')}. {b.get('benchmark_name', '?')}",
            "",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| Build Success | {'YES' if b.get('build_success') else 'NO'} |",
            f"| Test Success | {'YES' if b.get('test_success') else 'NO'} |",
            f"| APK Generated | {'YES (' + str(b.get('apk_size_bytes', 0)) + ' bytes)' if b.get('apk_generated') else 'NO'} |",
            f"| Runtime Validation | {'PASS' if b.get('runtime_validation') else 'SKIP/FAIL'} |",
            f"| Repair Cycles | {b.get('repair_cycles', 0)} |",
            f"| Total Errors | {b.get('total_errors', 0)} |",
            f"| Errors Repaired | {b.get('repaired_errors', 0)} |",
            f"| Unresolved Errors | {b.get('unresolved_errors', 0)} |",
            f"| Fix Rate | {b.get('fix_rate_pct', 0)}% |",
            f"| Pattern Memory Hits | {b.get('pattern_memory_hits', 0)} |",
            f"| Pattern Memory Total | {b.get('pattern_memory_total', 0)} |",
            f"| Legacy Failure Memory | {b.get('failure_memory_size', 0)} entries |",
            f"| Pattern Generalizations | {b.get('pattern_generalizations', 0)} |",
            f"| Files Generated | {b.get('files_generated', 0)} |",
            f"| Completion Time | {b.get('completion_time_s', 0)}s |",
            f"| Goal Status | {b.get('goal_status', '?')} |",
            f"| Goal Result | {b.get('goal_result', 'N/A')} |",
            "",
        ])

    lines.append("---")
    lines.append("")
    lines.append("*Report generated by scripts/benchmark_android.py*")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
