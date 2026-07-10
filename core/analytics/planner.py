"""PlannerAnalytics — aggregate performance metrics across all plans, 
strategies, outcomes, and replan events.

Pulls from PlanStore, PlanOutcomeStore, SchedulerStore, and KnowledgeStore
to answer:

  - Was the planner correct?
  - Which strategy works best?
  - Is confidence calibrated?
  - Which risks actually matter?
  - Are replans improving outcomes?
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from core.planner.store import PlanStore
from core.planner.outcomes import PlanOutcomeStore

logger = logging.getLogger(__name__)


class PlannerAnalytics:
    """Aggregate performance analytics for the planning system."""

    def __init__(self) -> None:
        self._plan_store = PlanStore()
        self._outcome_store = PlanOutcomeStore()

    # ── Public API ──────────────────────────────────────────────────────────

    def compute(self) -> dict[str, Any]:
        """Compute all planner performance metrics."""
        outcomes = self._get_all_outcomes()
        plans = self._plan_store.list_all()

        with_actuals = [o for o in outcomes if o.get("actual_success") is not None]

        return {
            "overall": self._compute_overall(with_actuals, len(outcomes)),
            "strategy_win_rates": self._compute_strategy_win_rates(plans, with_actuals),
            "accuracy_trend": self._compute_accuracy_trend(with_actuals),
            "confidence_calibration": self._compute_confidence_calibration(with_actuals),
            "duration_accuracy": self._compute_duration_accuracy(with_actuals),
            "risk_accuracy": self._compute_risk_accuracy(with_actuals),
            "replan_metrics": self._compute_replan_metrics(plans, outcomes),
            "failure_analysis": self._compute_failure_analysis(with_actuals),
            "computed_at": datetime.utcnow().isoformat(),
        }

    # ── Data loading ──────────────────────────────────────────────────────

    def _get_all_outcomes(self) -> list[dict[str, Any]]:
        """Fetch all outcome rows from the database."""
        import sqlite3
        from core.storage import SYSTEM_DB
        db = SYSTEM_DB
        try:
            with sqlite3.connect(db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM plan_outcomes ORDER BY created_at DESC"
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.debug("Could not load outcomes: %s", e)
            return []

    # ── Metric computers ──────────────────────────────────────────────────

    def _compute_overall(
        self, outcomes: list[dict], total_plans: int
    ) -> dict[str, Any]:
        """Overall planner performance across all completed plans."""
        if not outcomes:
            return {"total_plans": 0, "message": "No completed plans yet"}

        n = len(outcomes)
        successes = sum(1 for o in outcomes if o.get("actual_success"))
        failures = sum(1 for o in outcomes if o.get("actual_success") == 0)
        success_rate = round(successes / max(n, 1), 3)

        # Average accuracy — computed in-memory from loaded outcomes
        # (avoids N+1 SQLite queries that get_prediction_accuracy would do)
        accuracies = []
        for o in outcomes:
            try:
                acc = self._fast_prediction_accuracy(o)
                if acc is not None:
                    accuracies.append(acc)
            except Exception:
                pass
        avg_accuracy = round(sum(accuracies) / max(len(accuracies), 1), 3) if accuracies else None

        return {
            "total_plans": total_plans,
            "completed_plans": n,
            "successful": successes,
            "failed": failures,
            "success_rate": success_rate,
            "avg_prediction_accuracy": avg_accuracy,
        }

    @staticmethod
    def _fast_prediction_accuracy(outcome: dict) -> float | None:
        """Compute overall prediction accuracy from a single outcome dict.

        Pure in-memory — no SQLite queries. Mirrors get_prediction_accuracy
        logic but avoids loading from DB.
        """
        if outcome.get("actual_success") is None:
            return None

        scores = []

        # 1. Success prediction accuracy
        predicted_success = outcome.get("predicted_confidence", 0.5) >= 0.5
        actual_success = bool(outcome["actual_success"])
        scores.append(1.0 if predicted_success == actual_success else 0.0)

        # 2. Duration accuracy
        actual_duration_sec = outcome.get("actual_duration_seconds")
        predicted_duration_days = outcome.get("predicted_duration_days")
        if actual_duration_sec is not None and predicted_duration_days:
            actual_hours = actual_duration_sec / 3600
            actual_days = actual_hours / 8
            if actual_days > 0:
                ratio = min(predicted_duration_days, actual_days) / max(predicted_duration_days, actual_days)
                scores.append(ratio)

        # 3. Risk accuracy
        actual_failures = outcome.get("actual_failures")
        if actual_failures is not None:
            predicted_risk = outcome.get("predicted_risk_score", 0.5)
            actual_risk = min(1.0, actual_failures / max(outcome.get("predicted_duration_days", 5) * 2, 1))
            risk_diff = abs(predicted_risk - actual_risk)
            scores.append(max(0.0, 1.0 - risk_diff))

        return round(sum(scores) / max(len(scores), 1), 3) if scores else None

    def _compute_strategy_win_rates(
        self, plans: list[dict], outcomes: list[dict]
    ) -> list[dict[str, Any]]:
        """Success rate grouped by strategy type."""
        # Map plan_id -> inferred strategy
        plan_strategies: dict[str, str] = {}
        for p in plans:
            root = p.get("root_node", {})
            if isinstance(root, str):
                try:
                    import json
                    root = json.loads(root)
                except Exception:
                    root = {}
            strat = root.get("strategy") or self._infer_strategy(p.get("goal", ""))
            plan_strategies[p["id"]] = strat

        strategy_stats: dict[str, dict] = {}
        for o in outcomes:
            pid = o["plan_id"]
            strat = plan_strategies.get(pid, "unknown")
            if strat not in strategy_stats:
                strategy_stats[strat] = {"total": 0, "successful": 0, "failed": 0}
            strategy_stats[strat]["total"] += 1
            if o.get("actual_success"):
                strategy_stats[strat]["successful"] += 1
            else:
                strategy_stats[strat]["failed"] += 1

        result = []
        for strat, stats in sorted(
            strategy_stats.items(), key=lambda x: x[1]["total"], reverse=True
        ):
            rate = round(stats["successful"] / max(stats["total"], 1), 3)
            result.append({
                "strategy": strat,
                "total": stats["total"],
                "successful": stats["successful"],
                "failed": stats["failed"],
                "win_rate": rate,
            })
        return result

    def _compute_accuracy_trend(
        self, outcomes: list[dict]
    ) -> dict[str, Any]:
        """How accuracy changes over time (last 10 completed plans)."""
        if not outcomes:
            return {"direction": "stable", "recent": [], "message": "No data"}

        recent = outcomes[:10]  # most recent first
        accuracies = []
        for o in recent:
            try:
                from core.planner.outcomes import get_prediction_accuracy
                acc = get_prediction_accuracy(o["plan_id"])
                if acc and acc.get("has_actuals"):
                    accuracies.append({
                        "plan_id": o["plan_id"],
                        "accuracy": acc["overall_accuracy"],
                        "completed_at": o.get("completed_at", o.get("created_at", "")),
                    })
            except Exception:
                pass

        if len(accuracies) < 2:
            return {"direction": "stable", "recent": accuracies}

        # Compare first half vs second half
        mid = len(accuracies) // 2
        early = [a["accuracy"] for a in accuracies[mid:]]
        recent_scores = [a["accuracy"] for a in accuracies[:mid]]
        early_avg = sum(early) / max(len(early), 1)
        recent_avg = sum(recent_scores) / max(len(recent_scores), 1)

        if recent_avg > early_avg + 0.05:
            direction = "improving"
        elif recent_avg < early_avg - 0.05:
            direction = "declining"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "early_avg": round(early_avg, 3),
            "recent_avg": round(recent_avg, 3),
            "recent": accuracies[:10],
        }

    def _compute_confidence_calibration(
        self, outcomes: list[dict]
    ) -> dict[str, Any]:
        """How well does predicted confidence match actual success rate."""
        if not outcomes:
            return {"status": "no_data", "message": "No completed plans"}

        # Group by confidence bucket
        buckets: dict[str, dict] = {
            "0-20%": {"range": (0, 0.2), "total": 0, "successful": 0},
            "20-40%": {"range": (0.2, 0.4), "total": 0, "successful": 0},
            "40-60%": {"range": (0.4, 0.6), "total": 0, "successful": 0},
            "60-80%": {"range": (0.6, 0.8), "total": 0, "successful": 0},
            "80-100%": {"range": (0.8, 1.0), "total": 0, "successful": 0},
        }

        for o in outcomes:
            conf = o.get("predicted_confidence", 0.5)
            for label, b in buckets.items():
                lo, hi = b["range"]
                if lo <= conf < hi:
                    b["total"] += 1
                    if o.get("actual_success"):
                        b["successful"] += 1
                    break

        calibration = []
        calibration_errors = []
        for label, b in buckets.items():
            if b["total"] == 0:
                continue
            actual_rate = b["successful"] / b["total"]
            mid = (b["range"][0] + b["range"][1]) / 2
            error = abs(actual_rate - mid)
            calibration.append({
                "bucket": label,
                "total": b["total"],
                "predicted_center": round(mid, 2),
                "actual_success_rate": round(actual_rate, 2),
                "error": round(error, 2),
            })
            calibration_errors.append(error)

        avg_error = round(sum(calibration_errors) / max(len(calibration_errors), 1), 3) if calibration_errors else None

        if avg_error is None:
            status = "no_data"
        elif avg_error <= 0.10:
            status = "well_calibrated"
        elif avg_error <= 0.20:
            status = "moderately_calibrated"
        else:
            status = "poorly_calibrated"

        return {
            "status": status,
            "avg_calibration_error": avg_error,
            "buckets": calibration,
        }

    def _compute_duration_accuracy(self, outcomes: list[dict]) -> dict:
        """Predicted vs actual duration comparison."""
        with_duration = [
            o for o in outcomes
            if o.get("actual_duration_seconds") is not None
            and o.get("predicted_duration_days", 0) > 0
        ]
        if not with_duration:
            return {"status": "no_data", "message": "No duration data yet"}

        errors = []
        for o in with_duration:
            pred_days = o["predicted_duration_days"]
            actual_days = o["actual_duration_seconds"] / 3600 / 8  # 8h work days
            error = abs(actual_days - pred_days) / max(pred_days, 1)
            errors.append(error)

        avg_error = round(sum(errors) / max(len(errors), 1), 3)
        total_over = sum(1 for e in errors if e > 0.25)  # >25% error

        return {
            "status": "good" if avg_error < 0.25 else "moderate" if avg_error < 0.5 else "poor",
            "avg_duration_error": avg_error,
            "plans_with_duration_data": len(with_duration),
            "significantly_wrong": total_over,
        }

    def _compute_risk_accuracy(self, outcomes: list[dict]) -> dict:
        """Predicted risk score vs actual failure rate."""
        with_risk = [
            o for o in outcomes
            if o.get("predicted_risk_score", 0) > 0
            and o.get("actual_success") is not None
        ]
        if not with_risk:
            return {"status": "no_data", "message": "No risk data yet"}

        # High risk plans should fail more often
        high_risk = [o for o in with_risk if o["predicted_risk_score"] >= 0.5]
        low_risk = [o for o in with_risk if o["predicted_risk_score"] < 0.5]

        high_fail_rate = sum(1 for o in high_risk if not o["actual_success"]) / max(len(high_risk), 1)
        low_fail_rate = sum(1 for o in low_risk if not o["actual_success"]) / max(len(low_risk), 1)
        risk_discrimination = high_fail_rate - low_fail_rate

        return {
            "high_risk_plans": len(high_risk),
            "low_risk_plans": len(low_risk),
            "high_risk_failure_rate": round(high_fail_rate, 3),
            "low_risk_failure_rate": round(low_fail_rate, 3),
            "risk_discrimination": round(risk_discrimination, 3),
            "discrimination_quality": "good" if risk_discrimination > 0.2 else "moderate" if risk_discrimination > 0.05 else "poor",
        }

    def _compute_replan_metrics(
        self, plans: list[dict], outcomes: list[dict]
    ) -> dict[str, Any]:
        """How often plans are replanned and with what effect."""
        replanned = [p for p in plans if p.get("status") == "draft"]
        # Also check outcome records for plans that were replanned
        replan_count = 0
        for p in plans:
            root = p.get("root_node", {})
            if isinstance(root, str):
                try:
                    import json
                    root = json.loads(root)
                except Exception:
                    root = {}
            if root.get("last_replanned"):
                replan_count += 1

        total_plans = len(plans)
        rate = round(replan_count / max(total_plans, 1), 3)

        # Check if replans led to better outcomes
        improved_after_replan = 0
        replanned_plans = [p for p in plans if p.get("root_node", {}).get("last_replanned")] if plans else []
        # Simplified: any replanned plan with successful outcome is counted
        outcome_map = {o["plan_id"]: o for o in outcomes}
        for p in replanned_plans:
            o = outcome_map.get(p["id"])
            if o and o.get("actual_success"):
                improved_after_replan += 1

        return {
            "total_plans": total_plans,
            "replanned_count": replan_count,
            "replan_rate": rate,
            "improved_after_replan": improved_after_replan,
            "avg_replans_per_plan": round(replan_count / max(total_plans, 1), 2),
        }

    def _compute_failure_analysis(self, outcomes: list[dict]) -> dict:
        """Common patterns among failed plans."""
        failed = [o for o in outcomes if o.get("actual_success") == 0]
        if not failed:
            return {"total_failures": 0, "patterns": [], "common_reasons": []}

        # Analyze: what was predicted for failed plans?
        patterns = []
        for o in failed:
            reasons = []
            if o.get("predicted_confidence", 1.0) < 0.4:
                reasons.append("low_confidence")
            if o.get("predicted_risk_score", 0) > 0.7:
                reasons.append("high_risk")
            if o.get("predicted_duration_days", 0) > 14:
                reasons.append("long_duration")
            patterns.append({
                "plan_id": o["plan_id"],
                "predicted_confidence": o.get("predicted_confidence"),
                "predicted_risk": o.get("predicted_risk_score"),
                "predicted_duration_days": o.get("predicted_duration_days"),
                "actual_failures": o.get("actual_failures"),
                "reasons": reasons or ["unknown"],
            })

        # Aggregate common reasons
        from collections import Counter
        all_reasons = [r for p in patterns for r in p["reasons"]]
        reason_counts = Counter(all_reasons)

        return {
            "total_failures": len(failed),
            "patterns": patterns[:10],
            "common_reasons": [
                {"reason": reason, "count": count}
                for reason, count in reason_counts.most_common()
            ],
        }

    @staticmethod
    def _infer_strategy(goal: str) -> str:
        """Infer strategy from goal text."""
        g = goal.lower()
        if "flutter" in g or "dart" in g:
            return "flutter"
        if "react" in g or "typescript" in g:
            return "react_native"
        if "native" in g or "kotlin" in g or "android" in g:
            return "native_android"
        if "pwa" in g or "web" in g or "progressive" in g:
            return "web_pwa"
        if "ios" in g or "swift" in g:
            return "ios_native"
        if "backend" in g or "api" in g:
            return "backend_first"
        return "unknown"
