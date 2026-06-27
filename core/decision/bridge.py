"""StrategyBridge — wiring adapter between decision engine and strategy pipeline.

Maps the strategy v2 pipeline (TradeoffEngine, OutcomePredictor, StrategicSelector)
into the evidence dimensions consumed by the UnifiedDecisionModel. This is the
integration seam that allows the decision engine to leverage existing strategic
reasoning without duplicating it.
"""

from __future__ import annotations

import logging
from typing import Any

from core.decision.models import EvidenceDimension
from core.strategy_v2.models import StrategyCandidate, TradeoffAnalysis
from core.strategy_v2.tradeoffs import TradeoffEngine
from core.strategy_v2.predictor import OutcomePredictor
from core.strategy_v2.selector import StrategicSelector

logger = logging.getLogger(__name__)


class StrategyBridge:
    """Bridges strategy v2 reasoning into decision evidence dimensions.

    Converts strategy_v2 outputs (tradeoff comparisons, predictions,
    selections) into EvidenceDimension objects that the
    UnifiedDecisionModel can consume.

    This avoids duplicating strategic reasoning inside the decision
    engine while still making it available as evidence.
    """

    def __init__(
        self,
        tradeoff_engine: TradeoffEngine | None = None,
        predictor: OutcomePredictor | None = None,
        selector: StrategicSelector | None = None,
    ):
        self._tradeoff = tradeoff_engine
        self._predictor = predictor
        self._selector = selector

    def dimension_for_strategy(
        self,
        candidate: StrategyCandidate,
        weight: float = 0.15,
    ) -> EvidenceDimension:
        """Score a single strategy candidate as an evidence dimension.

        Uses candidate.overall_improvement and candidate.confidence.
        If a predictor is wired, it is called first to refine the
        candidate (v2 predictor mutates the candidate in place).
        """
        cand = candidate

        if self._predictor is not None:
            try:
                cand = self._predictor.predict(candidate)
            except Exception as e:
                logger.debug("Strategy prediction error: %s", e)

        score = cand.overall_improvement * max(0.1, cand.confidence)
        reasons = [
            f"Improvement: {cand.overall_improvement:.0%} "
            f"risk: {cand.risk:.0%} cost: {cand.implementation_cost:.0%}",
        ]

        return EvidenceDimension(
            name="strategy_alignment",
            score=max(0.0, min(1.0, score)),
            weight=weight,
            reason="; ".join(reasons),
            confidence=cand.confidence,
            source="strategy_v2",
        )

    def dimension_for_tradeoff(
        self,
        candidates: list[StrategyCandidate],
        weight: float = 0.10,
    ) -> EvidenceDimension:
        """Score relative strategy fitness via tradeoff comparison.

        Computes each candidate's relative position in the tradeoff
        space and returns the overall fitness as a 0-1 score.
        """
        if self._tradeoff is None or len(candidates) < 2:
            return EvidenceDimension(
                name="tradeoff_fitness",
                score=0.5, weight=weight,
                reason="Tradeoff engine not available or insufficient candidates",
                confidence=0.0, source="strategy_v2",
            )

        try:
            analyses = self._tradeoff.analyze_all(candidates)
            if analyses:
                utilities = [a.net_utility for a in analyses]
                max_u = max(utilities) if utilities else 0.0
                min_u = min(utilities) if utilities else 0.0
                # Normalize to [0, 1] if range > 0, else 0.5
                if max_u > min_u:
                    norm = (max_u - min_u) / max_u if max_u > 0 else 0.5
                else:
                    norm = 0.5
                notes = analyses[0].tradeoff_notes if analyses else "Tradeoff complete"
                return EvidenceDimension(
                    name="tradeoff_fitness",
                    score=max(0.0, min(1.0, norm)),
                    weight=weight,
                    reason=notes[:200],
                    confidence=0.5,
                    source="strategy_v2",
                )
        except Exception as e:
            logger.debug("Tradeoff comparison error: %s", e)

        return EvidenceDimension(
            name="tradeoff_fitness",
            score=0.5, weight=weight,
            reason="Tradeoff comparison produced no ranking",
            confidence=0.0, source="strategy_v2",
        )

    def rank_templates(
        self,
        template_ids: list[str],
        template_candidates: dict[str, list[StrategyCandidate]],
    ) -> list[tuple[str, float]]:
        """Rank templates by their best candidate's overall_improvement.

        Each template may have multiple strategy candidates; the best
        one's improvement score is used.
        """
        try:
            rankings: list[tuple[str, float]] = []
            for tid in template_ids:
                candidates = template_candidates.get(tid, [])
                if not candidates:
                    rankings.append((tid, 0.5))
                    continue

                best = max(c.overall_improvement for c in candidates)
                rankings.append((tid, best))

            rankings.sort(key=lambda x: x[1], reverse=True)
            return rankings
        except Exception as e:
            logger.debug("Template ranking error: %s", e)
            return [(tid, 0.5) for tid in template_ids]
