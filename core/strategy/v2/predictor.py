"""Outcome prediction for v2 strategies (Phase 15.1)."""
from __future__ import annotations

from typing import List, Tuple

from core.strategy.v2.models import StrategyCandidate, TimeHorizon


class OutcomePredictor:
    """Assign a time horizon and improvement range to candidates."""

    def predict(self, candidate: StrategyCandidate) -> StrategyCandidate:
        cost = candidate.implementation_cost
        risk = candidate.risk
        if cost >= 0.6 or risk >= 0.6:
            candidate.time_horizon = TimeHorizon.LONG_TERM
        elif cost <= 0.25 and risk <= 0.25:
            candidate.time_horizon = TimeHorizon.SHORT_TERM
        else:
            candidate.time_horizon = TimeHorizon.MEDIUM_TERM
        return candidate

    def predict_all(self, candidates: List[StrategyCandidate]) -> List[StrategyCandidate]:
        for candidate in candidates or []:
            self.predict(candidate)
        return candidates

    def estimate_improvement_range(
        self, candidate: StrategyCandidate
    ) -> Tuple[float, float]:
        spread = (1.0 - candidate.confidence) * candidate.overall_improvement
        pessimistic = candidate.overall_improvement - spread
        optimistic = candidate.overall_improvement + spread
        return pessimistic, optimistic
