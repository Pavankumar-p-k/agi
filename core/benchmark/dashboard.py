"""Regression Dashboard — cross-benchmark trend tracking.

Reads from:
  1. SQLite benchmark_runs table (orchestrated benchmark)
  2. JSON report files in benchmark_reports/ (specialized benchmarks)

Outputs a single markdown report comparing previous vs current baselines.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPORT_DIR = "benchmark_reports"
BM_DB = "data/benchmark.db"


def _list_json_reports(pattern: str) -> list[dict[str, Any]]:
    """List JSON report files matching a pattern, sorted by timestamp desc."""
    results: list[dict[str, Any]] = []
    if not os.path.isdir(REPORT_DIR):
        return results
    for fname in os.listdir(REPORT_DIR):
        if not re.search(pattern, fname) or not fname.endswith(".json"):
            continue
        fpath = os.path.join(REPORT_DIR, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        results.append({"file": fname, "path": fpath, "data": data})
    results.sort(key=lambda r: r["file"], reverse=True)
    return results


def _latest_json(pattern: str) -> dict[str, Any] | None:
    reports = _list_json_reports(pattern)
    return reports[0] if reports else None


def _sql_query(query: str, params: list[Any] | None = None) -> list[tuple]:
    if not os.path.isfile(BM_DB):
        return []
    try:
        conn = sqlite3.connect(BM_DB)
        rows = conn.execute(query, params or []).fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def _safe_num(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
        return 0.0 if f != f else f
    except (TypeError, ValueError):
        return default


def _task_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract task list from arbitrary benchmark JSON format."""
    for key in ("tasks", "results", "runs", "entries"):
        val = data.get(key)
        if isinstance(val, list):
            return val
    return []


def _model_benchmark_summary() -> list[dict[str, Any]]:
    """Summarize unified benchmark results per model from SQLite."""
    rows = _sql_query(
        "SELECT model_id, mode, status, COUNT(*) FROM benchmark_runs GROUP BY model_id, mode, status ORDER BY model_id, mode"
    )
    models: dict[str, dict[str, Any]] = {}
    for r in rows:
        mid, mode, status, cnt = r[0], r[1], r[2], r[3]
        if mid not in models:
            models[mid] = {"raw_total": 0, "raw_pass": 0, "arch_total": 0, "arch_pass": 0}
        key = "raw" if mode == "raw" else "arch"
        models[mid][f"{key}_total"] += cnt
        if status == "passed":
            models[mid][f"{key}_pass"] += cnt

    results = []
    for mid, v in sorted(models.items()):
        results.append({
            "model": mid,
            "raw_rate": round(v["raw_pass"] / max(v["raw_total"], 1) * 100, 1),
            "arch_rate": round(v["arch_pass"] / max(v["arch_total"], 1) * 100, 1),
            "gain": round((v["arch_pass"] / max(v["arch_total"], 1) - v["raw_pass"] / max(v["raw_total"], 1)) * 100, 1),
        })
    return results


def _success(t: dict[str, Any]) -> bool:
    for key in ("task_success", "success", "passed", "status"):
        val = t.get(key)
        if isinstance(val, bool):
            return val
        if isinstance(val, str) and val == "passed":
            return True
    return False


def _browser_benchmark_summary() -> dict[str, Any]:
    """Summarize latest browser benchmark."""
    report = _latest_json(r"browser_bench.*\.json")
    if not report:
        return {}
    data = report["data"]
    tasks = _task_list(data)
    n = len(tasks) or 1
    return {
        "source": report["file"],
        "pass_rate": round(sum(1 for t in tasks if _success(t)) / n * 100, 1),
        "tool_accuracy": round(sum(_safe_num(t.get("tool_selection_accuracy", t.get("tool_accuracy", 0))) for t in tasks) / n * 100, 1),
        "avg_turns": round(sum(_safe_num(t.get("turns", t.get("turn_count", 0))) for t in tasks) / n, 1),
        "avg_duration": round(sum(_safe_num(t.get("duration_seconds", t.get("duration", 0))) for t in tasks) / n, 1),
    }


def _long_horizon_summary() -> dict[str, Any]:
    """Summarize latest long-horizon benchmark."""
    report = _latest_json(r"long_horizon.*\.json")
    if not report:
        return {}
    data = report["data"]
    tasks = _task_list(data)
    n = len(tasks) or 1
    phases_total = 0
    for t in tasks:
        phases_total += _safe_num(t.get("phases_completed", t.get("phase_count", t.get("fsm_phases_completed", 0))))
    return {
        "source": report["file"],
        "pass_rate": round(sum(1 for t in tasks if _success(t)) / n * 100, 1),
        "avg_phases": round(phases_total / n, 1),
        "avg_duration": round(sum(_safe_num(t.get("duration_seconds", t.get("duration", 0))) for t in tasks) / n, 1),
    }


def _research_summary() -> dict[str, Any]:
    """Summarize latest research benchmark (prefers pipeline+fsm)."""
    report = _latest_json(r"research_quality.*\.json")
    if not report:
        return {}
    data = report["data"]
    tasks = data.get("tasks", [])

    configs: dict[str, list[dict]] = {}
    for t in tasks:
        cfg = t.get("config", "unknown")
        configs.setdefault(cfg, []).append(t)

    result: dict[str, Any] = {"source": report["file"]}
    for cfg, ctasks in configs.items():
        n = len(ctasks) or 1
        result[f"{cfg}_recall"] = round(sum(_safe_num(t.get("fact_recall", 0)) for t in ctasks) / n * 100, 1)
        result[f"{cfg}_hallucinations"] = sum(_safe_num(t.get("hallucinations", 0)) for t in ctasks)
        result[f"{cfg}_duration"] = round(sum(_safe_num(t.get("duration_seconds", 0)) for t in ctasks) / n, 1)
    return result


def _ablation_summary() -> dict[str, Any]:
    """Summarize latest ablation benchmark."""
    report = _latest_json(r"ablation.*\.json")
    if not report:
        return {}
    data = report["data"]
    tasks = _task_list(data)
    configs: dict[str, list[dict]] = {}
    for t in tasks:
        cfg = t.get("config", t.get("mode", "unknown"))
        configs.setdefault(cfg, []).append(t)
    result: dict[str, Any] = {"source": report["file"]}
    for cfg, ctasks in configs.items():
        n = len(ctasks) or 1
        result[f"{cfg}_rate"] = round(sum(1 for t in ctasks if _success(t)) / n * 100, 1)
    return result


def generate() -> str:
    """Generate the regression dashboard markdown report."""
    lines: list[str] = [
        "# Regression Dashboard",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## 1. Unified Benchmark (Model × Architecture)",
        "",
        "| Model | Raw | +Architecture | Gain |",
        "|-------|-----|---------------|------|",
    ]

    model_summary = _model_benchmark_summary()
    total_raw = total_arch = total_count = 0
    for m in model_summary:
        lines.append(f"| {m['model']:20s} | {m['raw_rate']:5.1f}% | {m['arch_rate']:5.1f}% | {m['gain']:+.1f}% |")
        total_raw += m["raw_rate"]
        total_arch += m["arch_rate"]
        total_count += 1

    if total_count:
        lines.append(f"| {'Average':20s} | {total_raw/total_count:5.1f}% | {total_arch/total_count:5.1f}% | {total_arch/total_count - total_raw/total_count:+.1f}% |")

    lines.extend(["", "---", "", "## 2. Browser Benchmark", ""])
    bs = _browser_benchmark_summary()
    if bs:
        lines.append(f"- **Source:** {bs['source']}")
        lines.append(f"- **Pass Rate:** {bs['pass_rate']}%")
        lines.append(f"- **Tool Accuracy:** {bs['tool_accuracy']}%")
        lines.append(f"- **Avg Turns:** {bs['avg_turns']}")
        lines.append(f"- **Avg Duration:** {bs['avg_duration']}s")
    else:
        lines.append("*No browser benchmark data found*")

    lines.extend(["", "---", "", "## 3. Long-Horizon Benchmark", ""])
    lh = _long_horizon_summary()
    if lh:
        lines.append(f"- **Source:** {lh['source']}")
        lines.append(f"- **Pass Rate:** {lh['pass_rate']}%")
        lines.append(f"- **Avg Phases Completed:** {lh['avg_phases']}")
        lines.append(f"- **Avg Duration:** {lh['avg_duration']}s")
    else:
        lines.append("*No long-horizon benchmark data found*")

    lines.extend(["", "---", "", "## 4. Research Quality Benchmark", ""])
    rs = _research_summary()
    if rs:
        lines.append(f"- **Source:** {rs['source']}")
        for key in sorted(rs.keys()):
            if key == "source":
                continue
            lines.append(f"- **{key}:** {rs[key]}")
    else:
        lines.append("*No research benchmark data found*")

    lines.extend(["", "---", "", "## 5. Ablation Benchmark", ""])
    abl = _ablation_summary()
    if abl:
        lines.append(f"- **Source:** {abl['source']}")
        for key in sorted(abl.keys()):
            if key == "source":
                continue
            lines.append(f"- **{key}:** {abl[key]}")
    else:
        lines.append("*No ablation benchmark data found*")

    lines.extend([
        "",
        "---",
        "",
        "## Legend",
        "",
        "- **Raw:** Model only, no architecture stack",
        "- **+Architecture:** Model + full JARVIS pipeline",
        "- **Gain:** Architecture pass rate minus raw pass rate",
        "",
        "*Auto-generated by JARVIS Regression Dashboard*",
    ])

    return "\n".join(lines)


def save(path: str = "docs/REGRESSION_DASHBOARD.md") -> str:
    report = generate()
    with open(path, "w") as f:
        f.write(report)
    logger.info("Dashboard saved to %s", path)
    return path


if __name__ == "__main__":
    path = save()
    print(generate())
