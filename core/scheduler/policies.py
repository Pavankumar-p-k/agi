"""PriorityPolicy — deterministic scoring engine for scheduler decisions.

Avoids AI. Uses static weights with activity-state modifiers.

Score = priority_weight + urgency_weight + retry_weight
        + waiting_time_bonus + user_requested_bonus + intelligence_boost

Phase 8.3D: adds DecisionPriorityPolicy that replaces the flat additive
score with expected-value-based scoring from the DecisionEngine bridge.

DecisionPriorityPolicy:
    score = expected_value * success_probability * confidence / resource_cost
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from core.scheduler.models import ScheduledActivity

if TYPE_CHECKING:
    from core.scheduler.decision import DecisionEngine
    from core.scheduler.intelligence import ActivityIntelligence

logger = logging.getLogger(__name__)

# Weights — tuned for "failed/stale first" behavior
PRIORITY_WEIGHTS: dict[int, int] = {
    0: 0,
    1: 20,
    2: 40,
    3: 60,
    4: 80,
    5: 100,
}

URGENCY_BONUS = 30
RETRY_BONUS = 50
WAITING_BONUS_PER_MINUTE = 2
USER_REQUESTED_BONUS = 80


class PriorityPolicy:
    """Deterministic activity ranking.

    Integrates optional ActivityIntelligence for learned priority boost
    based on historical success rate and expected duration per node_type.

    Usage:
        policy = PriorityPolicy()
        ranked = policy.rank(activities)
        best = ranked[0]  # highest score

        # With intelligence:
        policy = PriorityPolicy(intelligence=ActivityIntelligence())
    """

    def __init__(
        self,
        weights: dict[str, int] | None = None,
        intelligence: ActivityIntelligence | None = None,
    ):
        self._weights = weights or {}
        self._intelligence = intelligence

    @property
    def intelligence(self) -> ActivityIntelligence | None:
        return self._intelligence

    @intelligence.setter
    def intelligence(self, ai: ActivityIntelligence | None) -> None:
        self._intelligence = ai

    def rank(self, activities: list[ScheduledActivity],
             now: datetime | None = None) -> list[ScheduledActivity]:
        """Score each activity and return them sorted descending by score."""
        now = now or datetime.utcnow()
        for act in activities:
            act.score = self._score(act, now)
        ranked = sorted(activities, key=lambda a: a.score, reverse=True)
        if ranked:
            logger.debug("PriorityPolicy: top=%s score=%d status=%s",
                         ranked[0].activity_id, ranked[0].score, ranked[0].status)
        return ranked

    def _score(self, act: ScheduledActivity, now: datetime) -> int:
        score = 0

        # 1. Priority weight
        score += PRIORITY_WEIGHTS.get(act.priority, 0)

        # 2. Urgency — bonus for resumed activities that need continuation
        if act.status in ("pending", "running"):
            score += URGENCY_BONUS

        # 3. Retry weight — failed activities get a boost to retry
        if act.metadata.get("previous_status") == "failed":
            score += RETRY_BONUS

        # 4. Waiting time — linear bonus for stale activities
        if act.last_resumed_at:
            mins_since_resume = (now - act.last_resumed_at).total_seconds() / 60
            score += int(mins_since_resume * WAITING_BONUS_PER_MINUTE)
        elif act.created_at:
            mins_since_creation = (now - act.created_at).total_seconds() / 60
            score += int(mins_since_creation * WAITING_BONUS_PER_MINUTE)

        # 5. User-requested bonus
        if act.node_type == "goal" or act.metadata.get("source") == "user":
            score += USER_REQUESTED_BONUS

        # 6. Custom weights from constructor
        for key, weight in self._weights.items():
            if act.metadata.get(key):
                score += weight

        # 7. Intelligence boost — learned success_rate / duration tradeoff
        if self._intelligence:
            boost = self._intelligence.learned_priority(
                act.node_type, act.priority,
            )
            score += boost

        return score


class DecisionPriorityPolicy:
    """Expected-value-based priority scoring (Phase 8.3D).

    Replaces the flat additive score with decision-quality scoring:

        score = expected_value * success_probability * confidence / resource_cost

    The DecisionEngine bridge pulls signals from:
        - ActivityIntelligence (success_prob, duration, resources)
        - strategy_v2 (impact, risk, opportunity cost)
        - Opportunity pipeline (forecast, bottleneck)

    Usage:
        engine = DecisionEngine(intelligence=ActivityIntelligence())
        policy = DecisionPriorityPolicy(engine=engine)
        ranked = policy.rank(activities)
    """

    def __init__(
        self,
        engine: DecisionEngine | None = None,
        intelligence: ActivityIntelligence | None = None,
    ):
        from core.scheduler.decision import DecisionEngine as _DE
        self._engine = engine or _DE(intelligence=intelligence)

    @property
    def engine(self) -> DecisionEngine:
        return self._engine

    @engine.setter
    def engine(self, e: DecisionEngine) -> None:
        self._engine = e

    def rank(self, activities: list[ScheduledActivity],
             now: datetime | None = None) -> list[ScheduledActivity]:
        """Score each activity by expected value, return sorted descending."""
        for act in activities:
            act.score = self._score(act)
        ranked = sorted(activities, key=lambda a: a.score, reverse=True)
        if ranked:
            logger.debug("DecisionPriorityPolicy: top=%s score=%d type=%s",
                         ranked[0].activity_id, ranked[0].score, ranked[0].node_type)
        return ranked

    def _score(self, act: ScheduledActivity) -> int:
        """Compute decision-quality score for an activity.

        Returns 0–100 scaled integer for compatibility with existing
        priority system.
        """
        return self._engine.score(act)
