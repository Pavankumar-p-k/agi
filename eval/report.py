from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from eval.scorer import ScenarioScore

logger = logging.getLogger(__name__)


@dataclass
class EvalReport:
    run_timestamp: str
    scenarios: list[ScenarioScore]
    aggregate: float = 0.0
    passed: int = 0
    failed: int = 0
    avg_duration: float = 0.0
    avg_rounds: float = 0.0
    tool_accuracy_avg: float = 0.0
    pattern_match_avg: float = 0.0
    quality_avg: float = 0.0
    efficiency_avg: float = 0.0

    def __post_init__(self):
        if not self.scenarios:
            return
        n = len(self.scenarios)
        self.passed = sum(1 for s in self.scenarios if s.passed)
        self.failed = n - self.passed
        self.aggregate = sum(s.aggregate for s in self.scenarios) / n
        self.avg_duration = sum(s.total_duration for s in self.scenarios) / n
        self.avg_rounds = sum(s.round_count for s in self.scenarios) / n
        self.tool_accuracy_avg = sum(s.tool_call_accuracy for s in self.scenarios) / n
        self.pattern_match_avg = sum(s.pattern_match for s in self.scenarios) / n
        self.quality_avg = sum(s.quality_score for s in self.scenarios) / n
        self.efficiency_avg = sum(s.efficiency_score for s in self.scenarios) / n


def compare_runs(
    baseline_scores: list[ScenarioScore],
    current_scores: list[ScenarioScore],
) -> dict[str, Any]:
    baseline_map = {s.scenario_id: s for s in baseline_scores}
    current_map = {s.scenario_id: s for s in current_scores}

    all_ids = set(baseline_map) | set(current_map)
    regressions = []
    improvements = []
    new_failures = []
    new_passes = []

    for sid in sorted(all_ids):
        b = baseline_map.get(sid)
        c = current_map.get(sid)

        if b and c:
            diff = c.aggregate - b.aggregate
            entry = {"id": sid, "baseline": round(b.aggregate, 3), "current": round(c.aggregate, 3), "diff": round(diff, 3)}
            if diff < -0.1:
                entry["type"] = "regression"
                regressions.append(entry)
            elif diff > 0.1:
                entry["type"] = "improvement"
                improvements.append(entry)
            if b.passed and not c.passed:
                new_failures.append(sid)
            if not b.passed and c.passed:
                new_passes.append(sid)
        elif b is None:
            new_passes.append(sid)
        elif c is None:
            new_failures.append(sid)

    b_agg = sum(s.aggregate for s in baseline_scores) / max(len(baseline_scores), 1)
    c_agg = sum(s.aggregate for s in current_scores) / max(len(current_scores), 1)

    return {
        "baseline_count": len(baseline_scores),
        "current_count": len(current_scores),
        "baseline_aggregate": round(b_agg, 3),
        "current_aggregate": round(c_agg, 3),
        "aggregate_diff": round(c_agg - b_agg, 3),
        "regressions": regressions,
        "improvements": improvements,
        "new_failures": new_failures,
        "new_passes": new_passes,
    }


def print_report(report: EvalReport, comparison: dict | None = None) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append(f"EVAL REPORT — {report.run_timestamp}")
    lines.append("=" * 60)
    lines.append(f"  Aggregate:    {report.aggregate:.1%}")
    lines.append(f"  Passed:       {report.passed}/{len(report.scenarios)}")
    lines.append(f"  Failed:       {report.failed}/{len(report.scenarios)}")
    lines.append(f"  Avg duration: {report.avg_duration:.1f}s")
    lines.append(f"  Avg rounds:   {report.avg_rounds:.1f}")
    lines.append(f"  Tool acc:     {report.tool_accuracy_avg:.1%}")
    lines.append(f"  Pattern:      {report.pattern_match_avg:.1%}")
    lines.append(f"  Quality:      {report.quality_avg:.1%}")
    lines.append(f"  Efficiency:   {report.efficiency_avg:.1%}")

    if report.failed > 0:
        lines.append("")
        lines.append("FAILED SCENARIOS:")
        for s in report.scenarios:
            if not s.passed:
                lines.append(f"  ❌ {s.scenario_id}: {s.aggregate:.1%}")
                if s.error:
                    lines.append(f"     error: {s.error}")
                if s.tool_call_expected_missed:
                    lines.append(f"     missed tools: {s.tool_call_expected_missed}")
                if s.tool_call_forbidden_called:
                    lines.append(f"     forbidden called: {s.tool_call_forbidden_called}")
                if s.patterns_missed:
                    lines.append(f"     missed patterns: {s.patterns_missed}")

    if comparison:
        lines.append("")
        lines.append("REGRESSION COMPARISON:")
        lines.append(f"  Baseline:     {comparison['baseline_aggregate']:.1%}")
        lines.append(f"  Current:      {comparison['current_aggregate']:.1%}")
        lines.append(f"  Diff:         {comparison['aggregate_diff']:+.1%}")
        if comparison["regressions"]:
            lines.append(f"  Regressions:  {len(comparison['regressions'])}")
            for r in comparison["regressions"]:
                lines.append(f"    📉 {r['id']}: {r['baseline']:.1%} → {r['current']:.1%}")
        if comparison["improvements"]:
            lines.append(f"  Improvements: {len(comparison['improvements'])}")
            for r in comparison["improvements"]:
                lines.append(f"    📈 {r['id']}: {r['baseline']:.1%} → {r['current']:.1%}")

    lines.append("=" * 60)
    text = "\n".join(lines)
    print(text)
    return text
