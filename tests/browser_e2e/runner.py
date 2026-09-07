"""Runner for the browser E2E benchmark. Executes tasks through the agent loop."""
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from tests.browser_e2e.tasks import get_all_tasks
from tests.browser_e2e.metrics import Metrics

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("E2E_BENCH")

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("AGENT_MODEL", "qwen2.5:7b")
TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT", "180"))
RESULTS_FILE = _ROOT / "benchmarks" / "e2e_results.jsonl"


BROWSER_RELEVANT_TOOLS = frozenset({
    "browser_navigate", "browser_find", "browser_find_interactive",
    "browser_click", "browser_fill", "browser_press",
    "browser_snapshot", "browser_get_url", "browser_get_title",
    "browser_screenshot", "browser_current_state",
    "browser_evaluate", "browser_get_history", "browser_list_tabs",
    "browser_switch_tab", "browser_new_tab", "browser_close_tab",
    "browser_wait_visible", "browser_wait_text", "browser_wait_interactive",
    "browser_shadow_query", "browser_health", "vision_browser",
})


def _bootstrap_rbac():
    """Register developer role scopes if not already loaded."""
    from core.authz.engine import authz_engine
    from core.authz.schema import Role, Scope
    try:
        _ = authz_engine._role_definitions.get(Role.DEVELOPER)
        if not _:
            authz_engine.register_role(Role.DEVELOPER, {
                Scope.TOOLS_EXECUTE_MEDIUM, Scope.TOOLS_EXECUTE_LOW,
                Scope.FILES_READ, Scope.FILES_WRITE, Scope.MEMORY_READ,
                Scope.MEMORY_WRITE, Scope.SYSTEM_STATUS, Scope.PLUGINS_LIST,
                Scope.LLM_COMPLETE,
            })
            authz_engine.register_role(Role.OPERATOR, {"tools:execute:*"})
    except Exception as e:
        logger.warning("RBAC bootstrap failed: %s", e)


async def run_single_task(task, idx):
    """Run a single task through the agent loop. Returns (tool_calls, response, latency, error)."""
    from core.agent_loop import stream_agent_loop

    tool_calls = []
    full_response = ""
    error = None
    start = time.time()

    try:
        async for event in stream_agent_loop(
            endpoint_url=OLLAMA_URL,
            model=MODEL,
            messages=[{"role": "user", "content": task.prompt}],
            temperature=0.3,
            max_tokens=4096,
            max_rounds=3,
            relevant_tools=BROWSER_RELEVANT_TOOLS,
            owner="developer",
        ):
            if event.startswith("data: ") and not event.startswith("data: [DONE]"):
                try:
                    data = json.loads(event[6:])
                    dtype = data.get("type")
                    if dtype == "tool_calls":
                        calls = data.get("calls", [])
                        for c in calls:
                            tool_calls.append({
                                "name": c.get("name", ""),
                                "arguments": c.get("arguments", ""),
                            })
                    elif dtype == "tool_start":
                        tool_calls.append({
                            "name": data.get("tool", ""),
                            "arguments": data.get("command", ""),
                        })
                    elif dtype == "tool_call_delta":
                        pass
                    elif dtype == "delta" or not dtype:
                        delta = data.get("delta", data.get("content", ""))
                        if delta:
                            full_response += delta
                except json.JSONDecodeError:
                    pass
            elif event.startswith("event: error"):
                error = event.split("data: ", 1)[1] if "data: " in event else event
    except Exception as e:
        error = str(e)

    latency = time.time() - start
    return tool_calls, full_response, latency, error


def _generate_report(metrics):
    lines = []
    lines.append("# Browser E2E Benchmark Report")
    lines.append("")
    lines.append(f"**Model:** {MODEL}  |  **Ollama:** {OLLAMA_URL}")
    lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Tasks:** {metrics.total}  |  **Passed:** {metrics.passed}  |  **Failed:** {metrics.failed}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Overall Results")
    lines.append("")
    lines.append(f"| Metric | Value | Target | Status |")
    lines.append(f"|--------|-------|--------|--------|")
    ts_acc = metrics.tool_selection_accuracy()
    wc_acc = metrics.pass_rate
    ts_status = "PASS" if ts_acc >= 95 else "FAIL"
    wc_status = "PASS" if wc_acc >= 80 else "FAIL"
    e2e_status = "PASS" if wc_acc >= 75 else "FAIL"
    lines.append(f"| Tool Selection Accuracy | {ts_acc:.1f}% | >95% | {'[OK]' if ts_acc >= 95 else '[NO]'} |")
    lines.append(f"| Workflow Completion | {wc_acc:.1f}% | >80% | {'[OK]' if wc_acc >= 80 else '[NO]'} |")
    lines.append(f"| End-to-End Success Rate | {wc_acc:.1f}% | >75% | {'[OK]' if wc_acc >= 75 else '[NO]'} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per Category")
    lines.append("")
    lines.append("| Category | Pass | Total | Accuracy |")
    lines.append("|----------|------|-------|----------|")
    for cat, results in sorted(metrics.category_results.items()):
        acc = results["pass"] / results["total"] * 100 if results["total"] else 0
        bar = "#" * max(0, min(10, int(acc / 10))) + "." * max(0, 10 - min(10, int(acc / 10)))
        lines.append(f"| {cat:30s} | {results['pass']}/{results['total']} | {results['total']} | {acc:5.1f}% {bar} |")
    lines.append("")
    lines.append("## Tool Usage")
    lines.append("")
    lines.append("| Tool | Count |")
    lines.append("|------|-------|")
    for tool, count in metrics.tool_usage.most_common():
        bar = "#" * max(0, min(20, count // 2))
        lines.append(f"| {tool:35s} | {count:3d} {bar} |")
    lines.append("")
    lines.append("## Failure Reasons")
    lines.append("")
    lines.append("| Reason | Count |")
    lines.append("|--------|-------|")
    for reason, count in metrics.failure_reasons.most_common():
        lines.append(f"| {reason:40s} | {count:3d} |")
    lines.append("")
    lines.append("## Per-Task Results")
    lines.append("")
    lines.append("| # | Status | Category | Tools Used | Latency | Reason |")
    lines.append("|---|--------|----------|------------|---------|--------|")
    for t in metrics.tasks:
        status = "OK" if t["passed"] else "NO"
        tools = ", ".join(set(t["tool_calls"]))[:40] if t["tool_calls"] else "none"
        cat = t["category"][:25]
        reason = t["reason"][:30] if t["reason"] else ""
        lines.append(f"| {t['idx']:3d} | {status} | {cat:25s} | {tools:40s} | {t['latency']:5.1f}s | {reason:30s} |")
    return "\n".join(lines)


async def main():
    _bootstrap_rbac()
    tasks = get_all_tasks()
    metrics = Metrics()
    total = len(tasks)

    print(f"\n{'='*70}")
    print(f"Browser E2E Benchmark")
    print(f"Model: {MODEL}  |  Tasks: {total}")
    print(f"Results: {RESULTS_FILE}")
    print(f"{'='*70}\n")

    start_time = time.time()

    for i, task in enumerate(tasks):
        t_start = time.time()
        tool_calls, response, latency, error = await run_single_task(task, i)
        passed, reason = task.check_success(tool_calls, response) if not error else (False, "error:" + str(error)[:60])
        metrics.record_task(i, task, passed, reason, tool_calls, latency, response)

        # Write intermediate result
        with open(RESULTS_FILE, "a", encoding="utf-8") as f:
            record = {
                "idx": i,
                "category": task.category,
                "prompt": task.prompt[:80],
                "passed": passed,
                "reason": reason,
                "tool_calls": [tc.get("name", "") for tc in tool_calls],
                "latency": round(latency, 1),
            }
            f.write(json.dumps(record) + "\n")

        elapsed = time.time() - start_time
        eta = (elapsed / (i + 1)) * (total - i - 1) if i > 0 else 0
        tools_summary = ", ".join(set(tc.get("name", "") for tc in tool_calls))[:50] or "none"
        status = "[OK]" if passed else "[NO]"
        print(
            f"  [{i:3d}/{total}] {status} "
            f"pass:{metrics.pass_rate:5.1f}% "
            f"tools:[{tools_summary:50s}] "
            f"{latency:5.1f}s "
            f"ETA:{eta:6.0f}s  "
        )

    overall_elapsed = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"COMPLETE: {metrics.passed}/{metrics.total} passed ({metrics.pass_rate:.1f}%)")
    print(f"Tool Selection Accuracy: {metrics.tool_selection_accuracy():.1f}%")
    print(f"Duration: {overall_elapsed:.0f}s")
    print(f"{'='*70}\n")

    report = _generate_report(metrics)
    report_path = _ROOT / "docs" / "BROWSER_E2E_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
