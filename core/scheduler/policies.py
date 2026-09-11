from __future__ import annotations

from datetime import datetime
from typing import Any


class PriorityPolicy:
    def rank(self, activities: list[Any], now: datetime | None = None) -> list[Any]:
        now = now or datetime.now()
        for activity in activities:
            waiting = max(0.0, (now - activity.created_at).total_seconds() / 3600)
            retry = 2.0 if activity.metadata.get("previous_status") == "failed" else 0.0
            user = 1.0 if activity.node_type == "goal" else 0.0
            activity.score = activity.priority * 10.0 + retry + user + waiting
        return sorted(activities, key=lambda item: item.score, reverse=True)


class DecisionPriorityPolicy(PriorityPolicy):
    pass
