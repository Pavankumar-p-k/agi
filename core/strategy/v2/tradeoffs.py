"""Phase 15.2+ — Tradeoff Engine with Future Option Value.

Compares strategy candidates across multiple decision dimensions:

  - Improvement magnitude
  - Risk (failure probability)
  - Implementation cost (effort/resources)
  - Confidence (evidence strength)
  - Time horizon (short-term vs long-term payoff)
  - Opportunity cost (what is foregone by choosing this)
  - **Future option value** (what future opportunities this unlocks)

The option value dimension enables the system to answer:
    "Strategy A has lower utility than B, but A unlocks 3 future
     improvements. Is A still the better choice?"

This moves from static ranking to dynamic opportunity-aware selection.
"""

from __future__ import annotations

import logging
from typing import Any

from core.strategy.v2.models import (
    StrategyCandidate,
    TradeoffAnalysis,
)

logger = logging.getLogger(__name__)

# Default utility weights for the tradeoff dimensions
_DEFAULT_UTILITY_WEIGHTS: dict[str, float] = {
    "improvement": 0.35,
    "risk_penalty": -0.25,
    "cost_penalty": -0.15,
    "confidence": 0.15,
    "time_preference": 0.10,  # shorter = better
}

# Time horizon penalties (longer = more uncertainty, less utility)
_TIME_PENALTY: dict[str, float] = {
    "short_term": 1.0,
    "medium_term": 0.7,
    "long_term": 0.4,
}

# Discount factor for future option value by time horizon
# A strategy that enables a short-term future improvement retains
# more of that improvement's utility than one enabling a long-term
# improvement (more uncertainty, longer wait).
_FUTURE_DISCOUNT: dict[str, float] = {
    "short_term": 0.8,
    "medium_term": 0.5,
    "long_term": 0.2,
}

# Weight for option value in the net utility computation
# Kept conservative — option value is a bonus, not the primary driver
_OPTION_VALUE_WEIGHT: float = 0.10


class TradeoffEngine:
    """Analyzes tradeoffs between strategy candidates.

    For each candidate, computes a net utility score across all
    decision dimensions, identifies strengths and weaknesses,
    and produces a TradeoffAnalysis.
    """

    def __init__(self, utility_weights: dict[str, float] | None = None):
        self._weights = utility_weights or dict(_DEFAULT_UTILITY_WEIGHTS)

    def analyze(self, candidate: StrategyCandidate,
                opportunity_cost: float = 0.0,
                option_value: float = 0.0) -> TradeoffAnalysis:
        """Analyze a single candidate's tradeoffs and compute net utility.

        Args:
            candidate: The strategy to analyze.
            opportunity_cost: The utility of the best alternative (used to
                             compute opportunity cost penalty).
            option_value: The estimated future value of strategies this
                         candidate unlocks (used to compute option value bonus).

        Returns:
            TradeoffAnalysis with net utility and dimension scores.
        """
        dimension_scores: dict[str, float] = {}
        strengths: list[str] = []
        weaknesses: list[str] = []

        # 1. Improvement contribution
        improvement_score = (
            self._weights.get("improvement", 0.35) * candidate.overall_improvement
        )
        dimension_scores["improvement"] = improvement_score
        if candidate.overall_improvement > 0.5:
            strengths.append("improvement")
        elif candidate.overall_improvement < 0.2:
            weaknesses.append("improvement")

        # 2. Risk penalty
        risk_penalty = (
            abs(self._weights.get("risk_penalty", -0.25)) * candidate.risk
        )
        dimension_scores["risk"] = -risk_penalty
        if candidate.risk < 0.3:
            strengths.append("low_risk")
        elif candidate.risk > 0.6:
            weaknesses.append("high_risk")

        # 3. Cost penalty
        cost_penalty = (
            abs(self._weights.get("cost_penalty", -0.15)) * candidate.implementation_cost
        )
        dimension_scores["cost"] = -cost_penalty
        if candidate.implementation_cost < 0.3:
            strengths.append("low_cost")
        elif candidate.implementation_cost > 0.6:
            weaknesses.append("high_cost")

        # 4. Confidence contribution
        confidence_score = (
            self._weights.get("confidence", 0.15) * candidate.confidence
        )
        dimension_scores["confidence"] = confidence_score
        if candidate.confidence > 0.8:
            strengths.append("high_confidence")
        elif candidate.confidence < 0.5:
            weaknesses.append("low_confidence")

        # 5. Time horizon preference (shorter = better)
        time_penalty = _TIME_PENALTY.get(candidate.time_horizon.value, 0.7)
        time_score = (
            self._weights.get("time_preference", 0.10) * time_penalty
        )
        dimension_scores["time_horizon"] = time_score
        if candidate.time_horizon.value == "short_term":
            strengths.append("quick_win")
        elif candidate.time_horizon.value == "long_term":
            weaknesses.append("long_term")

        # 6. Opportunity cost penalty
        if opportunity_cost > 0:
            oc_penalty = min(opportunity_cost * 0.3, 0.3)
            dimension_scores["opportunity_cost"] = -oc_penalty
            if oc_penalty > 0.15:
                weaknesses.append("high_opportunity_cost")

        # 7. Future option value (what this strategy unlocks)
        if option_value > 0:
            ov_score = _OPTION_VALUE_WEIGHT * option_value
            dimension_scores["option_value"] = ov_score
            if ov_score > 0.05:
                strengths.append("high_option_value")
        else:
            dimension_scores["option_value"] = 0.0

        # Net utility
        net_utility = sum(dimension_scores.values())

        # Tradeoff notes
        notes = self._build_notes(candidate, dimension_scores,
                                  strengths, weaknesses, option_value)

        return TradeoffAnalysis(
            strategy_id=candidate.strategy_id,
            net_utility=net_utility,
            dimension_scores=dimension_scores,
            strengths=strengths,
            weaknesses=weaknesses,
            option_value=option_value,
            tradeoff_notes=notes,
        )

    def analyze_all(self, candidates: list[StrategyCandidate]
                    ) -> list[TradeoffAnalysis]:
        """Analyze tradeoffs for all candidates, computing opportunity costs.

        Three-pass analysis:
          1. Raw utilities (no opportunity cost, no option value)
          2. Compute future option values from enabled_strategy_ids
          3. Final analysis with opportunity cost and option value

        The option value computation discounts enabled strategies'
        utilities by their time horizon — short-term unlocks
        retain more value than long-term ones.
        """
        # Build lookup
        candidate_map = {c.strategy_id: c for c in candidates}

        # Pass 1: raw utilities without opportunity cost or option value
        pre_analyses = [self.analyze(c, opportunity_cost=0.0, option_value=0.0)
                        for c in candidates]
        pre_utilities = {a.strategy_id: a.net_utility for a in pre_analyses}

        # Pass 2: compute future option value for each candidate
        option_values: dict[str, float] = {}
        for candidate in candidates:
            ov = 0.0
            for enabled_id in candidate.enabled_strategy_ids:
                enabled = candidate_map.get(enabled_id)
                if enabled is None:
                    continue
                enabled_utility = pre_utilities.get(enabled_id, 0.0)
                if enabled_utility <= 0:
                    continue
                discount = _FUTURE_DISCOUNT.get(enabled.time_horizon.value, 0.5)
                ov += enabled_utility * discount
            option_values[candidate.strategy_id] = ov

        # Pass 3: with opportunity cost and option value
        analyses: list[TradeoffAnalysis] = []
        for candidate in candidates:
            other_utilities = [
                u for sid, u in pre_utilities.items()
                if sid != candidate.strategy_id
            ]
            best_alternative = max(other_utilities) if other_utilities else 0.0
            ov = option_values.get(candidate.strategy_id, 0.0)
            analysis = self.analyze(candidate,
                                    opportunity_cost=best_alternative,
                                    option_value=ov)
            analyses.append(analysis)

        return analyses

    def _build_notes(self, candidate: StrategyCandidate,
                     dimension_scores: dict[str, float],
                     strengths: list[str],
                     weaknesses: list[str],
                     option_value: float = 0.0) -> str:
        """Build a human-readable summary of the tradeoff analysis."""
        parts = [f"Strategy: {candidate.name}"]
        if strengths:
            parts.append(f"Strengths: {', '.join(strengths)}")
        if weaknesses:
            parts.append(f"Risks: {', '.join(weaknesses)}")
        parts.append(
            f"Net utility: {sum(dimension_scores.values()):.3f}"
        )
        if option_value > 0:
            parts.append(f"Option value: {option_value:.3f}")
        return " | ".join(parts)
