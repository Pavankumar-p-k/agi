"""PlannerImprovementDetector — consumes PlannerPerformance and generates
improvement opportunities specific to the planning system.

Detects:
  - Underperforming strategies (low win rate vs system average)
  - Poor confidence calibration (high calibration error)
  - Failure hotspots (repeated failure patterns)
  - Risk prediction errors (low discrimination)
  - Duration prediction drift
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.analytics.planner import PlannerAnalytics

logger = logging.getLogger(__name__)

# Thresholds
_MIN_PLANS_FOR_STRATEGY = 2
_LOW_WIN_RATE_THRESHOLD = 0.5
_HIGH_CALIBRATION_ERROR_THRESHOLD = 0.15
_GOOD_RISK_DISCRIMINATION = 0.15


class PlannerImprovementDetector:
    """Scans planner analytics for improvement opportunities."""

    def __init__(self) -> None:
        self._analytics = PlannerAnalytics()

    def detect_all(self) -> list[dict[str, Any]]:
        """Return all improvement opportunities."""
        performance = self._analytics.compute()
        opportunities: list[dict[str, Any]] = []

        opportunities.extend(self._detect_strategy_issues(performance))
        opportunities.extend(self._detect_calibration_issues(performance))
        opportunities.extend(self._detect_risk_issues(performance))
        opportunities.extend(self._detect_duration_issues(performance))
        opportunities.extend(self._detect_failure_hotspots(performance))

        return opportunities

    def _detect_strategy_issues(self, perf: dict) -> list[dict]:
        """Find strategies with win rate significantly below average."""
        opportunities = []
        win_rates = perf.get("strategy_win_rates", [])
        overall = perf.get("overall", {})

        overall_rate = overall.get("success_rate", 0.5)
        if not win_rates or overall_rate == 0:
            return []

        for s in win_rates:
            strat = s["strategy"]
            total = s["total"]
            win_rate = s["win_rate"]

            if total < _MIN_PLANS_FOR_STRATEGY:
                continue
            if win_rate >= _LOW_WIN_RATE_THRESHOLD:
                continue

            gap = overall_rate - win_rate
            impact = "high" if gap > 0.3 else "medium" if gap > 0.15 else "low"
            expected_gain = round(min(gap * 1.2, 0.5), 3)  # conservative improvement estimate

            opportunities.append({
                "id": f"opp_{uuid.uuid4().hex[:12]}",
                "type": "strategy_tuning",
                "strategy": strat,
                "description": f"'{strat}' underperforming ({s['successful']}/{s['total']} wins vs {overall_rate*100:.0f}% avg)",
                "current_value": round(win_rate, 3),
                "target_value": round(overall_rate, 3),
                "expected_gain": expected_gain,
                "impact": impact,
                "recommended_action": "reduce_strategy_weight",
                "recommended_change": f"Reduce {strat} recommendation weight to 0.5",
                "evidence": f"Win rate {win_rate*100:.0f}% vs system avg {overall_rate*100:.0f}% ({total} plans)",
                "detected_at": __import__("datetime").datetime.utcnow().isoformat(),
                "status": "open",
            })

        return opportunities

    def _detect_calibration_issues(self, perf: dict) -> list[dict]:
        """Find confidence calibration problems."""
        calib = perf.get("confidence_calibration", {})
        if calib.get("status") == "no_data":
            return []

        opportunities = []
        avg_error = calib.get("avg_calibration_error")

        if avg_error is not None and avg_error > _HIGH_CALIBRATION_ERROR_THRESHOLD:
            impact = "high" if avg_error > 0.25 else "medium"

            opportunities.append({
                "id": f"opp_{uuid.uuid4().hex[:12]}",
                "type": "calibration_adjustment",
                "strategy": None,
                "description": f"Confidence calibration error {avg_error*100:.0f}% exceeds threshold",
                "current_value": round(avg_error, 3),
                "target_value": round(_HIGH_CALIBRATION_ERROR_THRESHOLD, 3),
                "expected_gain": round(avg_error - _HIGH_CALIBRATION_ERROR_THRESHOLD, 3),
                "impact": impact,
                "recommended_action": "recalibrate_confidence",
                "recommended_change": "Adjust confidence formula to reduce over/under-confidence",
                "evidence": f"Calibration status: {calib.get('status', 'unknown')}",
                "detected_at": __import__("datetime").datetime.utcnow().isoformat(),
                "status": "open",
            })

        return opportunities

    def _detect_risk_issues(self, perf: dict) -> list[dict]:
        """Find risk prediction problems."""
        risk = perf.get("risk_accuracy", {})
        if risk.get("status") == "no_data":
            return []

        opportunities = []
        discrimination = risk.get("risk_discrimination", 0)

        if discrimination < _GOOD_RISK_DISCRIMINATION:
            impact = "medium"

            opportunities.append({
                "id": f"opp_{uuid.uuid4().hex[:12]}",
                "type": "risk_reweighting",
                "strategy": None,
                "description": "Risk scores poorly discriminate between successful and failed plans",
                "current_value": round(discrimination, 3),
                "target_value": round(_GOOD_RISK_DISCRIMINATION, 3),
                "expected_gain": round(_GOOD_RISK_DISCRIMINATION - discrimination, 3),
                "impact": impact,
                "recommended_action": "adjust_risk_scoring",
                "recommended_change": "Increase weight of high-correlation risk factors, reduce noise factors",
                "evidence": f"Risk discrimination: {discrimination:.1%} (high-risk fail: {risk.get('high_risk_failure_rate', 0):.0%}, low-risk: {risk.get('low_risk_failure_rate', 0):.0%})",
                "detected_at": __import__("datetime").datetime.utcnow().isoformat(),
                "status": "open",
            })

        return opportunities

    def _detect_duration_issues(self, perf: dict) -> list[dict]:
        """Find duration prediction problems."""
        dur = perf.get("duration_accuracy", {})
        if dur.get("status") == "no_data":
            return []

        opportunities = []
        if dur.get("status") == "poor":
            opportunities.append({
                "id": f"opp_{uuid.uuid4().hex[:12]}",
                "type": "duration_calibration",
                "strategy": None,
                "description": f"Duration predictions significantly off (avg error: {dur.get('avg_duration_error', 0)*100:.0f}%)",
                "current_value": round(dur.get("avg_duration_error", 0), 3),
                "target_value": 0.25,
                "expected_gain": round(max(dur.get("avg_duration_error", 0) - 0.25, 0), 3),
                "impact": "medium",
                "recommended_action": "adjust_duration_estimates",
                "recommended_change": "Apply correction factor to duration predictions based on historical error",
                "evidence": f"{dur.get('plans_with_duration_data', 0)} plans, {dur.get('significantly_wrong', 0)} off by >25%",
                "detected_at": __import__("datetime").datetime.utcnow().isoformat(),
                "status": "open",
            })

        return opportunities

    def _detect_failure_hotspots(self, perf: dict) -> list[dict]:
        """Find common failure patterns."""
        failures = perf.get("failure_analysis", {})
        total = failures.get("total_failures", 0)
        if total == 0:
            return []

        opportunities = []
        common = failures.get("common_reasons", [])
        for reason in common[:3]:
            if reason["count"] < 2:
                continue
            opportunities.append({
                "id": f"opp_{uuid.uuid4().hex[:12]}",
                "type": "failure_hotspot",
                "strategy": None,
                "description": f"Failure pattern '{reason['reason']}' occurred {reason['count']}x",
                "current_value": reason["count"],
                "target_value": 0,
                "expected_gain": round(min(reason["count"] / max(total, 1), 0.3), 3),
                "impact": "high" if reason["count"] >= total * 0.5 else "medium",
                "recommended_action": "address_failure_pattern",
                "recommended_change": f"Add pre-check for '{reason['reason'].replace('_', ' ')}' before approving plans",
                "evidence": f"Pattern appears in {reason['count']}/{total} failed plans",
                "detected_at": __import__("datetime").datetime.utcnow().isoformat(),
                "status": "open",
            })

        return opportunities
