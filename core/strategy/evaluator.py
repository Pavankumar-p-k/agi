"""Strategy scoring and ranking (Phase 12)."""
from __future__ import annotations

from typing import List, Optional, Tuple

from core.strategy.models import Prediction, Strategy


class StrategyEvaluator:
    """Score predictions and order strategies by desirability."""

    _W_SUCCESS = 0.4
    _W_RISK = 0.3
    _W_SPEED = 0.2
    _W_CONF = 0.1
    _SPEED_REFERENCE_DAYS = 10.0

    def score(self, prediction: Optional[Prediction]) -> float:
        if prediction is None:
            return 0.0

        success = max(0.0, min(1.0, prediction.success_probability))
        risk = max(0.0, min(1.0, prediction.estimated_risk))
        confidence = max(0.0, min(1.0, prediction.confidence))

        duration = prediction.estimated_duration_days or 0.0
        if duration <= 0:
            speed = 1.0
        else:
            speed = min(1.0, self._SPEED_REFERENCE_DAYS / duration)

        value = (
            self._W_SUCCESS * success
            + self._W_RISK * (1.0 - risk)
            + self._W_SPEED * speed
            + self._W_CONF * confidence
        )
        return max(0.0, min(1.0, value))

    def ordered(
        self, strategies: List[Strategy]
    ) -> List[Tuple[Strategy, float]]:
        scored = [
            (strategy, self.score(strategy.prediction))
            for strategy in strategies or []
            if strategy.prediction is not None
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored
