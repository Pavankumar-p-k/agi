from __future__ import annotations

from core.scheduler.models import ScheduledActivity


_STORES: dict[str, dict[str, ScheduledActivity]] = {}


class SchedulerStore:
    def __init__(self, db_path: str = "scheduler.db", **_kwargs):
        self._data = _STORES.setdefault(db_path, {})

    def save(self, activity: ScheduledActivity) -> ScheduledActivity:
        self._data[activity.activity_id] = activity
        return activity

    def get(self, activity_id: str) -> ScheduledActivity | None:
        return self._data.get(activity_id)

    def delete(self, activity_id: str) -> bool:
        return self._data.pop(activity_id, None) is not None

    def list(self) -> list[ScheduledActivity]:
        return list(self._data.values())
