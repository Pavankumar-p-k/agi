"""Queue — persistent, dependency-aware activity queue.

On each refresh:
  1. Load persisted activities from SchedulerStore
  2. Merge with active activities from ActivityManager
  3. Check dependencies, mark BLOCKED
  4. Score and sort the ready list
"""

from __future__ import annotations

import logging
from typing import Any

from core.activity.manager import ActivityManager
from core.scheduler.models import ScheduledActivity, activity_status_from_node
from core.scheduler.policies import PriorityPolicy
from core.scheduler.store import SchedulerStore

logger = logging.getLogger(__name__)


class SchedulerQueue:
    """Persistent activity queue with dependency resolution.

    Activities can be:
      - Submitted directly (via submit())
      - Loaded from the ActivityGraph (via refresh())
    """

    def __init__(self, activity_manager: ActivityManager,
                 store: SchedulerStore | None = None,
                 policy: PriorityPolicy | None = None):
        self._mgr = activity_manager
        self._store = store or SchedulerStore()
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

    def submit(self, activity_id: str, goal: str = "",
               priority: int = 0, node_type: str = "goal",
               depends_on: list[str] | None = None,
               metadata: dict[str, Any] | None = None,
               tenant_id: str = "") -> ScheduledActivity:
        """Submit a new activity directly to the queue (bypasses ActivityGraph)."""
        act = ScheduledActivity(
            activity_id=activity_id,
            priority=priority,
            status="pending",
            goal=goal,
            node_type=node_type,
            tenant_id=tenant_id,
            depends_on=depends_on or [],
            metadata=metadata or {},
        )
        self._store.add(act)
        self._activities[activity_id] = act
        return act

    def refresh(self) -> list[ScheduledActivity]:
        """Reload persisted + active activities, resolve deps, score.

        Returns the sorted ready list.
        """
        # 1. Load from SQLite store (submitted activities)
        stored = self._store.list_all()
        self._activities = {a.activity_id: a for a in stored}

        # 2. Merge with ActivityGraph activities
        try:
            nodes = self._mgr.get_active_activities()
            for node in nodes:
                nid = node.node_id
                if nid not in self._activities:
                    act = ScheduledActivity(
                        activity_id=nid,
                        priority=0,
                        status=activity_status_from_node(node.status),
                        goal=node.label,
                        node_type=node.node_type,
                        created_at=node.created_at,
                        metadata={"depth": node.depth},
                    )
                    self._activities[nid] = act
                    self._store.add(act)
        except Exception as e:
            logger.warning("SchedulerQueue: ActivityManager refresh failed: %s", e)

        # 3. Check dependencies
        self._ready = []
        self._blocked = []
        for act in self._activities.values():
            if act.status in ("completed", "cancelled", "failed"):
                continue
            if self._deps_satisfied(act):
                act.status = "pending"
                self._ready.append(act)
            else:
                act.block()
                self._blocked.append(act)

        # 4. Score and sort
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
            if dep and dep.status not in ("completed", "cancelled"):
                return False
            if dep is None:
                # Dependency doesn't exist in queue — check ActivityGraph
                pass
        return True

    def get_best(self) -> ScheduledActivity | None:
        """Return the highest-scored ready activity, or None."""
        if not self._ready:
            return None
        return self._ready[0]

    def get_best_n(self, n: int, exclude: set[str] | None = None) -> list[ScheduledActivity]:
        """Return the top N ready activities, excluding any in the exclude set."""
        if not self._ready:
            return []
        if exclude:
            candidates = [a for a in self._ready if a.activity_id not in exclude]
        else:
            candidates = list(self._ready)
        return candidates[:n]

    def get_best_n_chain_aware(self, n: int, exclude: set[str] | None = None
                                ) -> list[ScheduledActivity]:
        """Return top N ready activities, balanced across chains for parallelism.

        Strategy:
          1. Group ready activities by chain_id (metadata.chain_id).
          2. Pick the top activity from each chain (round-robin by chain).
          3. Fill remaining slots from top-scored ungrouped activities.

        This prevents one chain from consuming all worker slots.
        """
        if not self._ready:
            return []
        exclude = exclude or set()

        # Group by chain
        chains: dict[str, list[ScheduledActivity]] = {}
        ungrouped: list[ScheduledActivity] = []
        for act in self._ready:
            if act.activity_id in exclude:
                continue
            cid = act.metadata.get("chain_id")
            if cid:
                chains.setdefault(cid, []).append(act)
            else:
                ungrouped.append(act)

        selected: list[ScheduledActivity] = []
        chain_iterators = {cid: iter(acts) for cid, acts in chains.items()}

        # Round-robin: pick one from each chain
        while chain_iterators and len(selected) < n:
            for cid in list(chain_iterators.keys()):
                if len(selected) >= n:
                    break
                it = chain_iterators[cid]
                try:
                    selected.append(next(it))
                except StopIteration:
                    del chain_iterators[cid]

        # Fill remaining from ungrouped
        if len(selected) < n and ungrouped:
            selected.extend(ungrouped[: n - len(selected)])

        return selected[:n]

    def mark_running(self, activity_id: str) -> None:
        act = self._activities.get(activity_id)
        if act:
            act.status = "running"
            self._store.update_status(activity_id, "running")

    def mark_completed(self, activity_id: str) -> None:
        act = self._activities.get(activity_id)
        if act:
            act.status = "completed"
            self._store.update_status(activity_id, "completed")

    def mark_failed(self, activity_id: str) -> None:
        act = self._activities.get(activity_id)
        if act:
            act.status = "failed"
            act.metadata["previous_status"] = "failed"
            self._store.update_status(activity_id, "failed")
            self._store.update_metadata(activity_id, "previous_status", "failed")

    def cancel(self, activity_id: str) -> bool:
        """Cancel a pending or blocked activity. Returns True if found."""
        act = self._activities.get(activity_id)
        if act and act.status in ("pending", "blocked"):
            act.status = "cancelled"
            self._store.update_status(activity_id, "cancelled")
            self._ready = [a for a in self._ready if a.activity_id != activity_id]
            self._blocked = [a for a in self._blocked if a.activity_id != activity_id]
            return True
        return False

    def set_priority(self, activity_id: str, priority: int) -> bool:
        """Change priority of an activity. Returns True if found."""
        act = self._activities.get(activity_id)
        if act:
            act.priority = priority
            self._store.update_priority(activity_id, priority)
            return True
        return False
