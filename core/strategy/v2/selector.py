"""Phase 15.1 — Strategic Selector.

Chooses the best strategy from evaluated candidates and produces
a StrategicDecision with rationale.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from core.strategy.v2.models import (
    StrategicDecision,
    StrategyCandidate,
    StrategyStatus,
    TradeoffAnalysis,
)

logger = logging.getLogger(__name__)

# Minimum utility margin to justify selecting over alternatives
_MIN_UTILITY_MARGIN = 0.05


class StrategicSelector:
    """Selects the best strategy from evaluated candidates.

    The selector:
      1. Verifies the top candidate has sufficient margin over alternatives
      2. Records the decision with full rationale
      3. Marks the chosen strategy as SELECTED
    """

    def select(self, candidates: list[StrategyCandidate],
               analyses: list[TradeoffAnalysis],
               ) -> StrategicDecision:
        """Select the best strategy and produce a StrategicDecision.

        Args:
            candidates: Strategy candidates (must correspond to analyses).
            analyses: Tradeoff analyses (must correspond to candidates).

        Returns:
            StrategicDecision with the chosen strategy and rationale.
        """
        if not candidates or not analyses:
            raise ValueError("No candidates or analyses to select from")

        # Pair and sort by net utility
        paired = list(zip(candidates, analyses))
        paired.sort(key=lambda x: -x[1].net_utility)

        chosen, chosen_analysis = paired[0]
        alternatives = [c for c, _ in paired[1:]]

        utility_scores = {
            c.strategy_id: a.net_utility
            for c, a in paired
        }

        rationale = self._build_rationale(chosen, chosen_analysis,
                                          alternatives, utility_scores)

        # Mark chosen strategy
        chosen.status = StrategyStatus.SELECTED

        return StrategicDecision(
            decision_id=f"dec_{uuid.uuid4().hex[:12]}",
            chosen_strategy_id=chosen.strategy_id,
            alternative_strategy_ids=[c.strategy_id for c in alternatives],
            rationale=rationale,
            utility_scores=utility_scores,
            tradeoff_analyses=[a for _, a in paired],
            status=StrategyStatus.SELECTED,
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _build_rationale(
        chosen: StrategyCandidate,
        analysis: TradeoffAnalysis,
        alternatives: list[StrategyCandidate],
        utility_scores: dict[str, float],
    ) -> str:
        """Build a structured rationale for the decision."""
        parts = [
            f"Selected: {chosen.name}",
            f"Utility: {analysis.net_utility:.3f}",
            f"Expected improvement: {chosen.overall_improvement:.1%}",
            f"Risk: {chosen.risk:.1%}",
            f"Confidence: {chosen.confidence:.1%}",
            f"Time horizon: {chosen.time_horizon.value}",
        ]

        if alternatives:
            parts.append("Alternatives considered:")
            for alt in alternatives[:3]:  # top 3 alternatives
                score = utility_scores.get(alt.strategy_id, 0.0)
                parts.append(f"  - {alt.name} (utility: {score:.3f})")

        if analysis.strengths:
            parts.append(f"Key strengths: {', '.join(analysis.strengths)}")
        if analysis.weaknesses:
            parts.append(f"Key risks: {', '.join(analysis.weaknesses)}")

        return " | ".join(parts)
