"""Tradeoff analysis for v2 strategies (Phase 15.1-15.2)."""
from __future__ import annotations

from typing import Dict, List

from core.strategy.v2.models import StrategyCandidate, TimeHorizon, TradeoffAnalysis

_HORIZON_DISCOUNT = {
    "short_term": 0.8,
    "medium_term": 0.5,
    "long_term": 0.2,
}


class TradeoffEngine:
    """Compute net utility and explain strengths/weaknesses."""

    def analyze(self, candidate: StrategyCandidate) -> TradeoffAnalysis:
        improvement = candidate.overall_improvement * (
            0.5 + 0.5 * candidate.confidence
        )
        scores: Dict[str, float] = {
            "improvement": improvement,
            "risk": -candidate.risk,
            "cost": -candidate.implementation_cost * 0.5,
            "confidence": candidate.confidence * 0.1,
            "option_value": 0.0,
        }

        strengths: List[str] = []
        weaknesses: List[str] = []
        if candidate.overall_improvement >= 0.4:
            strengths.append("improvement")
        elif candidate.overall_improvement < 0.2:
            weaknesses.append("improvement")
        if candidate.risk <= 0.2:
            strengths.append("low_risk")
        elif candidate.risk >= 0.5:
            weaknesses.append("high_risk")
        if candidate.implementation_cost <= 0.3:
            strengths.append("low_cost")
        elif candidate.implementation_cost >= 0.6:
            weaknesses.append("high_cost")

        return TradeoffAnalysis(
            strategy_id=candidate.strategy_id,
            net_utility=sum(scores.values()),
            dimension_scores=scores,
            strengths=strengths,
            weaknesses=weaknesses,
            option_value=0.0,
        )

    def analyze_all(
        self, candidates: List[StrategyCandidate]
    ) -> List[TradeoffAnalysis]:
        base: Dict[str, TradeoffAnalysis] = {
            c.strategy_id: self.analyze(c) for c in (candidates or [])
        }
        by_id = {c.strategy_id: c for c in (candidates or [])}

        # Opportunity cost: strong alternatives make a strategy less attractive.
        for candidate in candidates or []:
            analysis = base[candidate.strategy_id]
            others = [
                base[o.strategy_id].net_utility
                for o in candidates
                if o.strategy_id != candidate.strategy_id
            ]
            best_other = max(others) if others else 0.0
            opportunity = -max(0.0, best_other - analysis.net_utility) * 0.1
            analysis.dimension_scores["opportunity_cost"] = opportunity
            analysis.net_utility = sum(analysis.dimension_scores.values())

        # Future option value: strategies that enable valuable successors.
        for candidate in candidates or []:
            analysis = base[candidate.strategy_id]
            option = 0.0
            for enabled_id in candidate.enabled_strategy_ids or []:
                target = base.get(enabled_id)
                if target is None or target.net_utility <= 0:
                    continue
                target_candidate = by_id.get(enabled_id)
                horizon = getattr(target_candidate.time_horizon, "value",
                                  target_candidate.time_horizon)
                option += target.net_utility * _HORIZON_DISCOUNT.get(horizon, 0.5)
            analysis.option_value = option
            analysis.dimension_scores["option_value"] = option
            analysis.net_utility = sum(analysis.dimension_scores.values())

        return [base[c.strategy_id] for c in (candidates or [])]
