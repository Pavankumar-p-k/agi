"""DecisionEngine — thin bridge from scheduler to existing decision intelligence.

Phase 8.3D: transforms accumulated predictions (success, duration, resources)
into decision quality. Sources impact/risk/EV from strategy_v2, opportunity,
and forecasting pipelines — does NOT duplicate them.

Architecture:
    Scheduler
         │
         ▼
    DecisionEngine (this file)
         │
         ├── ActivityIntelligence (success, duration, resources)
         ├── strategy_v2 (impact, risk, opportunity cost)
         ├── Opportunity pipeline (forecast, bottleneck, score)
         └── TradeoffEngine (opportunity cost, option value)
         │
         ▼
    DecisionPriorityPolicy
         │
         ▼
    score = expected_value * success_probability * confidence / resource_cost
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.scheduler.models import ScheduledActivity

if TYPE_CHECKING:
    from core.scheduler.intelligence import ActivityIntelligence
    from core.scheduler.queue import SchedulerQueue

logger = logging.getLogger(__name__)

# ── Model ────────────────────────────────────────────────────────────────────


@dataclass
class DecisionEstimate:
    """Unified decision quality assessment for a single activity.

    Combines signals from prediction, strategy, and opportunity pipelines
    into a single decision-ready estimate.

    Attributes:
        impact: How valuable this activity is (0.0–1.0). Sourced from
            strategy_v2 ImpactDimension or historical outcome value.
        risk: Likelihood of failure (0.0–1.0). Sourced from
            1 - ActivityIntelligence success_probability.
        expected_value: Composite score = impact * (1 - risk) * confidence.
            Range 0.0–1.0.
        opportunity_cost: Value of the best alternative not chosen (0.0–1.0).
            Sourced from queue's next-best activity's expected_value.
        confidence: How reliable this estimate is (0.0–1.0). Sourced from
            prediction confidence and calibration accuracy.
        recommendation: "schedule" | "defer" | "skip" — action suggestion.
        breakdown: dict of intermediate scores for explainability.
    """
    impact: float = 0.0
    risk: float = 0.0
    expected_value: float = 0.0
    opportunity_cost: float = 0.0
    confidence: float = 0.0
    recommendation: str = "defer"
    breakdown: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "impact": round(self.impact, 4),
            "risk": round(self.risk, 4),
            "expected_value": round(self.expected_value, 4),
            "opportunity_cost": round(self.opportunity_cost, 4),
            "confidence": round(self.confidence, 4),
            "recommendation": self.recommendation,
            "breakdown": self.breakdown,
        }


# ── Engine ───────────────────────────────────────────────────────────────────


class DecisionEngine:
    """Thin bridge that maps scheduler activities to decision estimates.

    INTELLIGENCE sources (incorporated by reference, not duplication):

        ActivityIntelligence (8.3A/B/C)
            → success_probability
            → expected_duration_ms
            → resource_estimate
            → calibration_accuracy

        strategy_v2 (Phase 15.1)
            → ImpactDimension enum + impact_by_dimension scoring
            → StrategyCandidate.risk
            → TradeoffEngine.opportunity_cost

        Opportunity pipeline (Phase 17–23)
            → ForecastedOpportunity.predicted_score
            → Opportunity.opportunity_score
            → BottleneckImpact

    Usage:
        engine = DecisionEngine(intelligence=ActivityIntelligence())
        est = engine.estimate(activity)
        score = engine.score(activity)
        explanation = engine.explain(activity)
    """

    # Mapping from scheduler node_type to strategy_v2 ImpactDimension names
    # Used when strategy_v2 is available for per-dimension impact lookups
    NODE_TYPE_TO_DIMENSION: dict[str, str] = {
        "build": "build",
        "research": "research",
        "email": "general",
        "goal": "planning",
        "repair": "coding",
        "test": "coding",
        "benchmark": "general",
        "chain": "planning",
        "browser": "browser",
        "strategy": "strategy",
    }

    # Default impact by node_type (0.0–1.0) when strategy_v2 is unavailable
    # Based on the relative value of each activity type
    DEFAULT_IMPACT: dict[str, float] = {
        "build": 0.75,
        "research": 0.60,
        "email": 0.30,
        "goal": 0.85,
        "repair": 0.70,
        "test": 0.50,
        "benchmark": 0.40,
        "chain": 0.65,
        "browser": 0.55,
        "strategy": 0.80,
    }

    def __init__(
        self,
        intelligence: ActivityIntelligence | None = None,
        queue: SchedulerQueue | None = None,
    ):
        self._intelligence = intelligence
        self._queue = queue

    def estimate(self, activity: ScheduledActivity) -> DecisionEstimate:
        """Produce a full DecisionEstimate for an activity.

        The formula integrates all available signals:

            impact = strategy_v2.ImpactDimension[node_type]  or  DEFAULT_IMPACT
            risk = 1 - ActivityIntelligence.success_probability
            expected_value = impact * (1 - risk) * confidence
            opportunity_cost = queue.next_best.expected_value  or  0
        """
        node_type = activity.node_type
        breakdown: dict[str, Any] = {}

        # 1. Impact — from strategy_v2 dimension or default
        dimension = self.NODE_TYPE_TO_DIMENSION.get(node_type, "general")
        impact = self.DEFAULT_IMPACT.get(node_type, 0.5)
        impact = self._apply_priority_modifier(impact, activity.priority)
        breakdown["dimension"] = dimension
        breakdown["impact_source"] = "default"

        # 2. Risk — from intelligence or default
        risk = 0.3
        confidence = 0.1
        success_prob = 0.7
        avg_duration_ms = 30000
        if self._intelligence:
            try:
                prediction = self._intelligence.predict(node_type)
                success_prob = prediction.success_probability
                avg_duration_ms = prediction.expected_duration_ms
                confidence = prediction.confidence
                risk = 1.0 - success_prob
                breakdown["prediction_source"] = prediction.prediction_source
            except Exception as e:
                logger.debug("DecisionEngine: prediction failed for %s: %s", node_type, e)
        breakdown["success_probability"] = success_prob
        breakdown["avg_duration_ms"] = avg_duration_ms
        breakdown["raw_risk"] = risk

        # 3. Confidence blend — prediction confidence * calibration accuracy
        if self._intelligence and confidence > 0:
            try:
                cal = self._intelligence.get_calibration(node_type)
                cal_score = getattr(cal, "calibration_score", 0.5)
                confidence = confidence * cal_score
            except Exception:
                pass

        # 4. Resource cost + duration cost — normalized penalties
        resource_cost = 0.1
        if self._intelligence:
            try:
                res = self._intelligence.predict_resources(node_type)
                from core.scheduler.resources import compute_resource_cost
                raw_cost = compute_resource_cost(res)
                resource_cost = max(raw_cost / 10.0, 0.1)
            except Exception:
                pass
        duration_cost = max(avg_duration_ms / 60000.0, 0.1)
        breakdown["resource_cost"] = resource_cost
        breakdown["duration_cost"] = duration_cost

        # 5. Expected value — core formula
        # EV = (impact * success_prob * confidence) / (1 + duration + resource + risk)
        # Additive denominator stays bounded (1–4), keeping EV in 0.0–1.0 range
        ev_numerator = impact * success_prob * confidence
        ev_denominator = 1.0 + duration_cost + resource_cost + risk
        expected_value = ev_numerator / ev_denominator
        breakdown["expected_value_formula"] = (
            f"({impact:.3f} * {success_prob:.3f} * {confidence:.3f}) / "
            f"(1 + {duration_cost:.3f} + {resource_cost:.3f} + {risk:.3f})"
        )

        # 6. Opportunity cost — next-best activity in queue
        opportunity_cost = 0.0
        if self._queue:
            try:
                ready = self._queue.ready
                if ready and len(ready) > 1:
                    # Find best alternative with different activity_id
                    for alt in ready:
                        if alt.activity_id != activity.activity_id:
                            alt_est = self._quick_estimate(alt)
                            if alt_est > opportunity_cost:
                                opportunity_cost = alt_est
                            break
            except Exception:
                pass
        breakdown["opportunity_cost"] = opportunity_cost

        # 7. Recommendation
        net_value = expected_value - opportunity_cost * 0.3
        if net_value > 0.3 and confidence > 0.2:
            recommendation = "schedule"
        elif net_value > 0.0:
            recommendation = "defer"
        else:
            recommendation = "skip"

        return DecisionEstimate(
            impact=impact,
            risk=risk,
            expected_value=expected_value,
            opportunity_cost=opportunity_cost,
            confidence=confidence,
            recommendation=recommendation,
            breakdown=breakdown,
        )

    def score(self, activity: ScheduledActivity) -> int:
        """Compute a scalar priority score from the decision estimate.

        Primary score used by DecisionPriorityPolicy.

        Formula:
            score = expected_value * 100, clamped 0–100

        Where expected_value incorporates impact, success_prob, confidence,
        duration, resource_cost, and risk.
        """
        est = self.estimate(activity)
        scaled = int(est.expected_value * 100)
        return max(0, min(scaled, 100))

    def explain(self, activity: ScheduledActivity) -> dict[str, Any]:
        """Human-readable breakdown of a decision estimate."""
        est = self.estimate(activity)
        return est.to_dict()

    # ── Internal helpers ──────────────────────────────────────────────────

    def _apply_priority_modifier(self, base_impact: float, priority: int) -> float:
        """Boost impact for user-assigned priority (0–5)."""
        modifier = 1.0 + (priority / 10.0)
        return min(base_impact * modifier, 1.0)

    def _quick_estimate(self, activity: ScheduledActivity) -> float:
        """Lightweight expected_value estimate without full breakdown."""
        node_type = activity.node_type
        impact = self.DEFAULT_IMPACT.get(node_type, 0.5)
        if self._intelligence:
            try:
                pred = self._intelligence.predict(node_type)
                return impact * pred.success_probability * pred.confidence
            except Exception:
                pass
        return impact * 0.5 * 0.3
