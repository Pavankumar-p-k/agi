"""StrategyEvaluator — deterministic scoring of strategies.

Score formula (configurable weights):
  score = success_probability * 0.40
        + (1.0 - risk) * 0.25
        + speed_score * 0.20
        + confidence * 0.15

All weights sum to 1.0. All metrics normalized to 0-1 range.
"""

from __future__ import annotations

import logging
from typing import Any

from core.strategy.models import Prediction, Strategy

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS: dict[str, float] = {
    "success_probability": 0.40,
    "risk": 0.25,       # inverted: higher risk → lower score
    "speed": 0.20,      # inverted: longer duration → lower score
    "confidence": 0.15,
}


class StrategyEvaluator:
    """Scores strategies using a deterministic, weighted formula."""

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or dict(DEFAULT_WEIGHTS)

    def score(self, prediction: Prediction) -> float:
        """Compute a single score from a prediction.

        Higher is better. All dimensions normalized 0-1.
        """
        if prediction is None:
            return 0.0

        success_dim = prediction.success_probability
        risk_dim = 1.0 - prediction.estimated_risk
        speed_dim = 1.0 - min(prediction.estimated_duration_days / 90.0, 1.0)
        conf_dim = prediction.confidence

        return (
            success_dim * self.weights.get("success_probability", 0.40)
            + risk_dim * self.weights.get("risk", 0.25)
            + speed_dim * self.weights.get("speed", 0.20)
            + conf_dim * self.weights.get("confidence", 0.15)
        )

    def ordered(self, strategies: list[Strategy]) -> list[tuple[Strategy, float]]:
        """Return strategies sorted by score descending.

        Each element: (strategy, score)
        """
        scored = [(s, self.score(s.prediction)) for s in strategies
                  if s.prediction is not None]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
