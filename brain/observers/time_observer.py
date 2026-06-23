from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from brain.events.event_bus import Event

from .observer_manager import Observer

logger = logging.getLogger(__name__)


class TimeObserver(Observer):
    """Time-based observer — emits events on cron-like schedules.

    Useful for daily maintenance, hourly checks, periodic self-reflection.
    """

    def __init__(self, poll_interval: float = 30.0, **kwargs):
        super().__init__(name="time_observer", poll_interval=poll_interval, **kwargs)
        self._schedules: list[dict] = []
        self._last_ticks: dict[str, str] = {}

    def add_schedule(self, name: str, cron_expr: str):
        """Add a named schedule.

        cron_expr: "daily@09:00", "hourly", "weekly@monday@09:00", "interval:300"
        """
        self._schedules.append({"name": name, "cron": cron_expr})
        logger.info("[TimeObserver] added schedule: %s = %s", name, cron_expr)

    def remove_schedule(self, name: str):
        self._schedules = [s for s in self._schedules if s["name"] != name]
        self._last_ticks.pop(name, None)

    async def observe(self) -> list[Event]:
        events: list[Event] = []
        now = datetime.now(timezone.utc)

        for schedule in self._schedules:
            name = schedule["name"]
            cron = schedule["cron"]
            last_key = f"{name}:{cron}"
            last_run = self._last_ticks.get(last_key)

            if self._is_due(cron, now, last_run):
                self._last_ticks[last_key] = now.isoformat()
                events.append(Event(
                    type="time.tick",
                    source="observer.time",
                    payload={
                        "schedule_name": name,
                        "cron": cron,
                        "timestamp": now.isoformat(),
                    },
                ))

        return events

    def _is_due(self, cron: str, now: datetime, last_run: str | None) -> bool:
        if cron.startswith("interval:"):
            try:
                seconds = int(cron.split(":", 1)[1])
            except (ValueError, IndexError):
                return False
            if last_run:
                last = datetime.fromisoformat(last_run)
                return (now - last).total_seconds() >= seconds
            return True

        if cron == "hourly":
            if last_run:
                last = datetime.fromisoformat(last_run)
                return (now - last).total_seconds() >= 3600
            return True

        if cron.startswith("daily@"):
            time_str = cron.split("@", 1)[1]
            parts = time_str.split(":")
            target_hour = int(parts[0])
            target_min = int(parts[1]) if len(parts) > 1 else 0
            if last_run:
                last = datetime.fromisoformat(last_run)
                if last.date() == now.date():
                    return False
            return now.hour == target_hour and now.minute == target_min

        if cron.startswith("weekly@"):
            parts = cron.split("@")
            day_map = {"monday": 0, "tuesday": 1, "wednesday": 2,
                       "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
            target_day = day_map.get(parts[1].lower(), now.weekday())
            time_str = parts[2] if len(parts) > 2 else "09:00"
            target_hour = int(time_str.split(":")[0])
            target_min = int(time_str.split(":")[1]) if ":" in time_str else 0
            if now.weekday() != target_day:
                return False
            if last_run:
                last = datetime.fromisoformat(last_run)
                if last.date() == now.date():
                    return False
            return now.hour == target_hour and now.minute == target_min

        return False
