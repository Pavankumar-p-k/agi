"""Queue — dependency-aware activity queue.

Filters blocked activities and maintains a sorted ready list.
"""

from __future__ import annotations

import logging
from typing import Any

from core.activity.manager import ActivityManager
from core.scheduler.models import ScheduledActivity
from core.scheduler.policies import PriorityPolicy

logger = logging.getLogger(__name__)


class SchedulerQueue:
    """Wraps priority ranking with dependency resolution.

    On each refresh:
      1. Load all active activities from ActivityManager
      2. For each, check if its dependencies are satisfied
      3. Mark BLOCKED activities whose deps are unmet
      4. Score and sort the ready (non-blocked) list
    """

    def __init__(self, activity_manager: ActivityManager,
                 policy: PriorityPolicy | None = None):
        self._mgr = activity_manager
        self._policy = policy or PriorityPolicy()
        self._activities: dict[str, ScheduledActivity] = {}
        self._ready: list[ScheduledActivity] = []
        self._blocked: list[ScheduledActivity] = []

    @property
    def ready(self) -> list[ScheduledActivity]:
        return self._ready

    @property
    def blocked(self) -> list[ScheduledActivity]:
        return self._blocked

    @property
    def all(self) -> list[ScheduledActivity]:
        return list(self._activities.values())

    def refresh(self) -> list[ScheduledActivity]:
        """Reload active activities from the store, resolve deps, score.

        Returns the sorted ready list.
        """
        nodes = self._mgr.get_active_activities()
        self._activities = {}
        for node in nodes:
            act = ScheduledActivity(
                activity_id=node.node_id,
                priority=0,
                status="pending",
                goal=node.label,
                node_type=node.node_type,
                created_at=node.created_at,
                last_resumed_at=None,
                metadata={
                    "depth": node.depth,
                    "previous_status": None,
                },
            )
            self._activities[node.node_id] = act

        # Check dependencies for each activity
        self._ready = []
        self._blocked = []
        for act in self._activities.values():
            if self._deps_satisfied(act):
                act.status = "pending"
                self._ready.append(act)
            else:
                act.block()
                self._blocked.append(act)

        # Score and sort ready list
        if self._ready:
            self._ready = self._policy.rank(self._ready)

        logger.debug("SchedulerQueue: %d ready, %d blocked, %d total",
                     len(self._ready), len(self._blocked), len(self._activities))
        return self._ready

    def _deps_satisfied(self, act: ScheduledActivity) -> bool:
        if not act.depends_on:
            return True
        for dep_id in act.depends_on:
            dep = self._activities.get(dep_id)
            if dep and dep.status != "completed":
                return False
        return True

    def get_best(self) -> ScheduledActivity | None:
        """Return the highest-scored ready activity, or None."""
        if not self._ready:
            return None
        return self._ready[0]

    def mark_running(self, activity_id: str) -> None:
        act = self._activities.get(activity_id)
        if act:
            act.status = "running"

    def mark_completed(self, activity_id: str) -> None:
        act = self._activities.get(activity_id)
        if act:
            act.status = "completed"

    def mark_failed(self, activity_id: str) -> None:
        act = self._activities.get(activity_id)
        if act:
            act.status = "failed"
            act.metadata["previous_status"] = "failed"
