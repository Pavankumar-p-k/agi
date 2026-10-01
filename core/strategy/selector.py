"""Strategy selection with reasoning (Phase 12)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from core.strategy.evaluator import StrategyEvaluator
from core.strategy.models import Strategy, StrategyDecision


class StrategySelector:
    """Pick the best-scoring strategy and explain why."""

    def __init__(self, evaluator: Optional[StrategyEvaluator] = None) -> None:
        self.evaluator = evaluator or StrategyEvaluator()

    def select(
        self, strategies: List[Strategy], goal: Optional[str] = None
    ) -> Tuple[Optional[Strategy], Optional[StrategyDecision]]:
        ordered = self.evaluator.ordered(strategies)
        if not ordered:
            return None, None

        chosen, score = ordered[0]
        resolved_goal = goal or (chosen.goal if chosen else "")

        decision = StrategyDecision(
            decision_id=f"sd_{uuid.uuid4().hex[:12]}",
            goal=resolved_goal,
            timestamp=datetime.now(timezone.utc),
            strategies_considered=list(strategies or []),
            chosen_strategy=chosen,
            confidence=score,
        )
        return chosen, decision

    def select_with_reasoning(
        self, strategies: List[Strategy], goal: Optional[str] = None
    ) -> dict:
        ordered = self.evaluator.ordered(strategies)
        if not ordered:
            return {
                "chosen": None,
                "reasoning": "No strategy with a prediction was available.",
                "ranking": [],
                "confidence": 0.0,
            }

        chosen, score = ordered[0]
        ranking = [
            {"name": strategy.name, "score": round(value, 4)}
            for strategy, value in ordered
        ]
        reasoning = (
            f"Selected '{chosen.name}' with score {score:.2f}: "
            f"success={chosen.prediction.success_probability:.2f}, "
            f"duration={chosen.prediction.estimated_duration_days:.1f}d, "
            f"risk={chosen.prediction.estimated_risk:.2f}."
        )
        return {
            "chosen": chosen,
            "reasoning": reasoning,
            "ranking": ranking,
            "confidence": score,
        }
