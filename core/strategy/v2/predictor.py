"""Phase 15.1 — Outcome Predictor.

Predicts the expected outcome of each strategy candidate using
evidence from similar past experiments, principle discrimination
scores, and confidence levels.

The predictor answers: "If we pursue this strategy, what is the
expected improvement, risk, and time to payoff?"
"""

from __future__ import annotations

import logging
from typing import Any

from core.strategy.v2.models import (
    StrategyCandidate,
    TimeHorizon,
)

logger = logging.getLogger(__name__)


class OutcomePredictor:
    """Predicts outcomes for strategy candidates.

    Uses the candidate's embedded evidence (from the proposals' principles)
    to estimate improvement, risk, and time horizon.
    """

    def predict(self, candidate: StrategyCandidate) -> StrategyCandidate:
        """Add or refine outcome predictions for a candidate.

        Currently uses the candidate's own evidence. Future versions
        will incorporate historical similarity from MemoryAdapter.

        Returns the same candidate (mutated) for chaining.
        """
        # Time horizon inference
        if candidate.implementation_cost < 0.3 and candidate.risk < 0.3:
            candidate.time_horizon = TimeHorizon.SHORT_TERM
        elif candidate.implementation_cost > 0.6 or candidate.risk > 0.6:
            candidate.time_horizon = TimeHorizon.LONG_TERM
        else:
            candidate.time_horizon = TimeHorizon.MEDIUM_TERM

        return candidate

    def predict_all(self, candidates: list[StrategyCandidate]
                    ) -> list[StrategyCandidate]:
        """Predict outcomes for all candidates."""
        return [self.predict(c) for c in candidates]

    def estimate_improvement_range(
        self, candidate: StrategyCandidate,
    ) -> tuple[float, float]:
        """Estimate a confidence interval for the improvement.

        Returns (pessimistic, optimistic) improvement values.
        """
        base = candidate.overall_improvement
        spread = (1.0 - candidate.confidence) * base
        pessimistic = max(0.0, base - spread)
        optimistic = min(1.0, base + spread)
        return (pessimistic, optimistic)
