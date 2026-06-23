"""StrategySelector — chooses the best strategy from evaluated candidates.

Selection rules:
  1. Highest score wins.
  2. Tiebreaker: prefer safer → prefer simpler → prefer more evidence.
  3. Returns chosen strategy, runner-up, confidence (score margin).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from core.strategy.evaluator import StrategyEvaluator
from core.strategy.models import Prediction, Strategy, StrategyDecision, StrategyTag

logger = logging.getLogger(__name__)


class StrategySelector:
    """Selects the best strategy from scored candidates."""

    def __init__(self, evaluator: StrategyEvaluator | None = None):
        self.evaluator = evaluator or StrategyEvaluator()

    def select(self, strategies: list[Strategy]) -> tuple[Strategy | None, StrategyDecision | None]:
        """Select the best strategy from a list.

        Returns:
          (chosen_strategy, decision_record)
        """
        if not strategies:
            logger.warning("StrategySelector: no strategies to select from")
            return None, None

        scored = self.evaluator.ordered(strategies)
        if not scored:
            return None, None

        chosen = scored[0][0]
        chosen_score = scored[0][1]

        runner_up = scored[1][0] if len(scored) > 1 else None
        runner_up_score = scored[1][1] if len(scored) > 1 else 0.0

        # Confidence = score margin over runner-up
        margin = chosen_score - runner_up_score if runner_up else chosen_score
        confidence = min(max(margin, 0.0) + 0.5, 0.99)

        decision = StrategyDecision(
            decision_id=f"sd_{uuid.uuid4().hex[:12]}",
            goal=chosen.goal,
            timestamp=datetime.utcnow(),
            strategies_considered=list(strategies),
            chosen_strategy=chosen,
            confidence=round(confidence, 3),
        )

        logger.info("StrategySelector: chose '%s' (score=%.3f, confidence=%.3f, %d candidates)",
                     chosen.name, chosen_score, confidence, len(scored))
        return chosen, decision

    def select_with_reasoning(self, strategies: list[Strategy]
                              ) -> dict[str, Any]:
        """Full selection result with reasoning trace.

        Returns a dict suitable for logging or display.
        """
        chosen, decision = self.select(strategies)

        if chosen is None:
            return {"chosen": None, "reasoning": "No strategies available"}

        scored = self.evaluator.ordered(strategies)

        ranking = [
            {
                "name": s.name,
                "score": round(score, 3),
                "prediction": s.prediction.to_dict() if s.prediction else None,
            }
            for s, score in scored
        ]

        runner_up = scored[1] if len(scored) > 1 else None

        reasoning_parts: list[str] = [
            f"Chosen: {chosen.name} (score={ranking[0]['score']})",
        ]
        if runner_up:
            reasoning_parts.append(
                f"Runner-up: {runner_up[0].name} (score={ranking[1]['score']})"
            )
        if chosen.prediction:
            p = chosen.prediction
            reasoning_parts.append(
                f"Predicted success: {p.success_probability:.0%}, "
                f"duration: {p.estimated_duration_days:.0f}d, "
                f"risk: {p.estimated_risk:.0%} (confidence: {p.confidence:.0%})"
            )

        return {
            "chosen": chosen.to_dict() if chosen else None,
            "confidence": round(decision.confidence, 3) if decision else 0,
            "ranking": ranking,
            "reasoning": "\n".join(reasoning_parts),
        }
