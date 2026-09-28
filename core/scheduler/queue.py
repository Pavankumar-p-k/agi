"""SchedulerQueue — tenant-partitioned priority queue of scheduled activities."""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Optional

from core.activity.manager import ActivityManager
from core.scheduler.models import ActivityStatus, ScheduledActivity


class SchedulerQueue:
    """Activities wait here, partitioned by tenant, ordered by priority."""

    def __init__(self, activity_manager: Optional[ActivityManager] = None) -> None:
        self.activity_manager = activity_manager or ActivityManager()
        self._queues: dict[str, "OrderedDict[str, ScheduledActivity]"] = {}
        self._lock = threading.Lock()

    # ── submission ───────────────────────────────────────────────────
    def submit(self, activity_id: str, goal: str, priority: int = 1,
               tenant_id: str = "default", **kwargs: object) -> ScheduledActivity:
        act = ScheduledActivity(
            activity_id=activity_id,
            goal=goal,
            priority=priority,
            tenant_id=tenant_id,
            status=ActivityStatus.READY,
            **kwargs,  # type: ignore[arg-type]
        )
        with self._lock:
            q = self._queues.setdefault(tenant_id, OrderedDict())
            q[activity_id] = act
        return act

    # ── consumption ──────────────────────────────────────────────────
    def pop_ready(self, tenant_id: Optional[str] = None) -> Optional[ScheduledActivity]:
        """Next ready activity for a tenant (or any tenant), priority first."""
        with self._lock:
            tenants = [tenant_id] if tenant_id else list(self._queues.keys())
            best: Optional[ScheduledActivity] = None
            for t in tenants:
                q = self._queues.get(t)
                if not q:
                    continue
                for act in q.values():
                    if act.is_ready and (best is None or act.priority > best.priority):
                        best = act
            if best is not None:
                self._queues[best.tenant_id].pop(best.activity_id, None)
            return best

    # ── introspection ────────────────────────────────────────────────
    @property
    def all(self) -> list[ScheduledActivity]:
        with self._lock:
            return [a for q in self._queues.values() for a in q.values()]

    def tenants(self) -> list[str]:
        with self._lock:
            return list(self._queues.keys())

    def __len__(self) -> int:
        return len(self.all)


__all__ = ["SchedulerQueue"]
