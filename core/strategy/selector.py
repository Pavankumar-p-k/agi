"""Minimal strategy selector surface."""
from __future__ import annotations

from datetime import datetime

from core.strategy.models import StrategyDecision


class StrategySelector:
    def select(self, goal: str, strategies):
        chosen = strategies[0] if strategies else None
        return chosen, StrategyDecision(
            decision_id="default_strategy",
            goal=goal,
            timestamp=datetime.utcnow(),
            strategies_considered=list(strategies),
            chosen_strategy=chosen,
            confidence=chosen.prediction.confidence if chosen else 0.0,
        )
