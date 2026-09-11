from __future__ import annotations

from core.scheduler.models import ScheduledActivity
from core.scheduler.policies import PriorityPolicy
from core.scheduler.store import SchedulerStore


class SchedulerQueue:
    def __init__(self, manager=None, store=None):
        self.manager = manager
        self.store = store or SchedulerStore()
        self._policy = PriorityPolicy()
        self._activities: dict[str, ScheduledActivity] = {}
        self._ready: list[ScheduledActivity] = []
        self._blocked: list[ScheduledActivity] = []

    @property
    def ready(self):
        return self._ready

    @property
    def blocked(self):
        return self._blocked

    @property
    def all(self):
        return list(self._activities.values())

    def get_best_n(self, count, exclude=None):
        excluded = exclude or set()
        return [item for item in self._ready if item.activity_id not in excluded][:count]

    def submit(self, activity_id, goal="", priority=0, depends_on=None, metadata=None):
        activity = ScheduledActivity(activity_id, goal=goal, priority=priority, metadata=metadata or {})
        activity.depends_on = list(depends_on or [])
        self._activities[activity_id] = self.store.save(activity)
        return activity

    def refresh(self):
        if self.manager is not None:
            for node in self.manager.get_active_activities():
                if node.node_id not in self._activities:
                    self._activities[node.node_id] = ScheduledActivity(node.node_id, goal=node.label, status="pending", node_type=node.node_type)
        else:
            self._activities.update({a.activity_id: a for a in self.store.list()})
        self._ready, self._blocked = [], []
        completed = {a.activity_id for a in self._activities.values() if a.status == "completed"}
        for activity in self._activities.values():
            deps = getattr(activity, "depends_on", [])
            if not activity.is_ready or any(dep not in completed for dep in deps):
                if activity.is_ready:
                    self._blocked.append(activity)
            else:
                self._ready.append(activity)
        self._ready = self._policy.rank(self._ready)
        return self._ready

    def get_best(self):
        return self._ready[0] if self._ready else None

    def mark_running(self, activity_id):
        activity = self._activities.get(activity_id) or self.store.get(activity_id)
        if not activity:
            return False
        activity.status = "running"
        self._activities[activity_id] = self.store.save(activity)
        return True

    def mark_failed(self, activity_id):
        activity = self._activities.get(activity_id) or self.store.get(activity_id)
        if not activity:
            return False
        activity.status = "failed"
        activity.metadata["previous_status"] = "failed"
        self.store.save(activity)
        return True

    def mark_completed(self, activity_id):
        activity = self._activities.get(activity_id) or self.store.get(activity_id)
        if not activity:
            return False
        activity.status = "completed"
        self.store.save(activity)
        return True

    def cancel(self, activity_id):
        activity = self._activities.get(activity_id) or self.store.get(activity_id)
        if not activity or activity.status == "running":
            return False
        activity.status = "cancelled"
        self.store.save(activity)
        self.refresh()
        return True

    def set_priority(self, activity_id, priority):
        activity = self._activities.get(activity_id) or self.store.get(activity_id)
        if not activity:
            return False
        activity.priority = priority
        self.store.save(activity)
        return True
