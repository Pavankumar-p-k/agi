"""Strategic selection for v2 (Phase 15.1)."""
from __future__ import annotations

import uuid
from typing import List

from core.strategy.v2.models import (
    StrategicDecision,
    StrategyCandidate,
    StrategyStatus,
)


class StrategicSelector:
    """Choose the highest-utility candidate and record a decision."""

    def select(
        self,
        candidates: List[StrategyCandidate],
        analyses: List,
    ) -> StrategicDecision:
        if not candidates:
            raise ValueError("Cannot select from an empty candidate list")

        by_id = {c.strategy_id: c for c in candidates}
        analysis_by_id = {a.strategy_id: a for a in (analyses or [])}
        ordered_ids = sorted(
            by_id.keys(),
            key=lambda sid: analysis_by_id[sid].net_utility if sid in analysis_by_id else 0.0,
            reverse=True,
        )
        chosen_id = ordered_ids[0]
        chosen = by_id[chosen_id]
        chosen.status = StrategyStatus.SELECTED

        utility_scores = {
            sid: (analysis_by_id[sid].net_utility if sid in analysis_by_id else 0.0)
            for sid in by_id
        }
        alternatives = ordered_ids[1:]
        best_utility = utility_scores[chosen_id]

        rationale = (
            f"Selected {chosen_id}: Utility {best_utility:.3f}. "
            f"Chosen for highest utility among {len(candidates)} candidates."
        )

        return StrategicDecision(
            decision_id=f"dec_{uuid.uuid4().hex[:12]}",
            chosen_strategy_id=chosen_id,
            alternative_strategy_ids=alternatives,
            rationale=rationale,
            utility_scores=utility_scores,
            status=StrategyStatus.SELECTED,
            tradeoff_analyses=list(analyses or []),
        )
