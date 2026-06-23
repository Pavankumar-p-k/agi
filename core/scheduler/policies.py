"""PriorityPolicy — deterministic scoring engine for scheduler decisions.

Avoids AI. Uses static weights with activity-state modifiers.

Score = priority_weight + urgency_weight + retry_weight
        + waiting_time_bonus + user_requested_bonus
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.scheduler.models import ScheduledActivity

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

    Usage:
        policy = PriorityPolicy()
        ranked = policy.rank(activities)
        best = ranked[0]  # highest score
    """

    def __init__(self, weights: dict[str, int] | None = None):
        self._weights = weights or {}

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

        return score
