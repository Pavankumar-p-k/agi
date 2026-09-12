"""DecisionRecorder: bridges routing decisions to the FeedbackStore.

Completed from the committed contract in tests/unit/test_provider_feedback.py
(DecisionRecorder section).  Owns no storage — delegates to FeedbackStore.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.providers.feedback.models import (
    RoutingDecision,
    RoutingOutcome,
    ScoreBreakdown,
)

logger = logging.getLogger(__name__)


class DecisionRecorder:
    """Record routing decisions (pre-execution) and outcomes (post-execution)."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def record_decision(
        self,
        capability: str,
        task: Optional[dict[str, Any]] = None,
        selected_provider: str = "",
        candidate_scores: Optional[list[ScoreBreakdown]] = None,
        goal: str = "",
        excluded_providers: Optional[list[str]] = None,
    ) -> RoutingDecision:
        decision = RoutingDecision(
            goal=goal or str((task or {}).get("goal", "") or ""),
            capability=capability,
            task=task or {},
            selected_provider=selected_provider,
            candidate_scores=candidate_scores or [],
            excluded_providers=excluded_providers or [],
        )
        self._store.save_decision(decision)
        return decision

    def record_outcome(
        self,
        decision_id: str,
        success: bool,
        duration_ms: float = 0.0,
        quality_score: float = 0.0,
        cost: float = 0.0,
        retries: int = 0,
        replan_level: int = 0,
    ) -> RoutingOutcome:
        outcome = RoutingOutcome(
            decision_id=decision_id,
            success=success,
            duration_ms=duration_ms,
            quality_score=quality_score,
            cost=cost,
            retries=retries,
            replan_level=replan_level,
        )
        self._store.save_outcome(outcome)
        return outcome

    def get_provider_performance(self, provider_id: str) -> dict[str, Any]:
        return self._store.get_provider_stats(provider_id)

    def get_recent_decisions(self, limit: int = 20) -> list[RoutingDecision]:
        return self._store.get_recent_decisions(limit=limit)
