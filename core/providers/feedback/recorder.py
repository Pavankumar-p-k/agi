from __future__ import annotations

import logging
import time
from typing import Any

from core.providers.feedback.models import RoutingDecision, RoutingOutcome, ScoreBreakdown
from core.providers.feedback.store import FeedbackStore

logger = logging.getLogger(__name__)


class DecisionRecorder:
    """Records routing decisions and their outcomes, linking them for
    downstream calibration analysis."""

    def __init__(self, store: FeedbackStore | None = None):
        from core.providers.feedback.store import FeedbackStore as _FS
        self._store = store or _FS()

    # ── Recording decisions ────────────────────────────────────────

    def record_decision(
        self,
        capability: str,
        task: dict[str, Any],
        selected_provider: str,
        candidate_scores: list[ScoreBreakdown],
        goal: str = "",
        excluded_providers: list[str] | None = None,
        provider_version: str = "",
    ) -> RoutingDecision:
        decision = RoutingDecision(
            goal=goal or task.get("goal", ""),
            capability=capability,
            task=task,
            selected_provider=selected_provider,
            candidate_scores=candidate_scores,
            excluded_providers=excluded_providers or [],
            timestamp=time.time(),
            provider_version=provider_version,
        )
        self._store.save_decision(decision)
        logger.debug(
            "[DecisionRecorder] Recorded decision %s: %s → %s (cap=%s)",
            decision.decision_id, capability, selected_provider, capability,
        )
        return decision

    # ── Recording outcomes ─────────────────────────────────────────

    def record_outcome(
        self,
        decision_id: str,
        success: bool,
        duration_ms: float = 0.0,
        quality_score: float = 0.0,
        cost: float = 0.0,
        error: str = "",
        retries: int = 0,
        replan_level: int = 0,
    ) -> RoutingOutcome:
        outcome = RoutingOutcome(
            decision_id=decision_id,
            success=success,
            duration_ms=duration_ms,
            quality_score=quality_score,
            cost=cost,
            error=error,
            retries=retries,
            replan_level=replan_level,
            timestamp=time.time(),
        )
        self._store.save_outcome(outcome)
        logger.debug(
            "[DecisionRecorder] Recorded outcome %s for decision %s: %s",
            outcome.outcome_id, decision_id, "PASS" if success else "FAIL",
        )
        return outcome

    # ── Query helpers ──────────────────────────────────────────────

    def get_provider_performance(
        self, provider_id: str, capability: str | None = None,
    ) -> dict[str, Any]:
        return self._store.get_provider_stats(provider_id, capability)

    def get_recent_decisions(self, limit: int = 20) -> list[RoutingDecision]:
        return self._store.get_recent_decisions(limit=limit)
