"""Phase 15.1 — Strategic Evaluator.

Scores strategy candidates using the TradeoffEngine and provides
a normalized ranking. The evaluator is the interface between
the tradeoff analysis and the final selection step.
"""

from __future__ import annotations

import logging
from typing import Any

from core.strategy.v2.models import StrategyCandidate, TradeoffAnalysis
from core.strategy.v2.tradeoffs import TradeoffEngine

logger = logging.getLogger(__name__)


class StrategicEvaluator:
    """Evaluates and ranks strategy candidates.

    Delegates per-candidate scoring to TradeoffEngine, then
    normalizes and ranks the results.
    """

    def __init__(self, tradeoff_engine: TradeoffEngine | None = None):
        self._tradeoff_engine = tradeoff_engine or TradeoffEngine()

    def evaluate(self, candidates: list[StrategyCandidate]
                 ) -> list[tuple[StrategyCandidate, TradeoffAnalysis]]:
        """Evaluate all candidates and return scored results.

        Returns list of (candidate, analysis) sorted by net utility descending.
        """
        analyses = self._tradeoff_engine.analyze_all(candidates)

        # Pair and sort
        paired = list(zip(candidates, analyses))
        paired.sort(key=lambda x: -x[1].net_utility)

        return paired
