"""Strategic evaluation for v2 (Phase 15.1)."""
from __future__ import annotations

from typing import List, Tuple

from core.strategy.v2.models import StrategyCandidate
from core.strategy.v2.tradeoffs import TradeoffEngine


class StrategicEvaluator:
    """Score candidates and return (candidate, analysis) sorted by utility."""

    def __init__(self, tradeoff_engine=None) -> None:
        self.tradeoffs = tradeoff_engine or TradeoffEngine()

    def evaluate(
        self, candidates: List[StrategyCandidate]
    ) -> List[Tuple[StrategyCandidate, object]]:
        candidates = list(candidates or [])
        analyses = {a.strategy_id: a for a in self.tradeoffs.analyze_all(candidates)}
        results = [(c, analyses[c.strategy_id]) for c in candidates]
        results.sort(key=lambda pair: pair[1].net_utility, reverse=True)
        return results
