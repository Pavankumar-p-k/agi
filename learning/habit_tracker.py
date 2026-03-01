import time
from collections import Counter
from datetime import datetime
from typing import Any


class HabitTracker:
    """
    Tracks recurring behavior and user-defined autonomous habits.
    """

    def __init__(self, memory):
        self.memory = memory
        self._events_by_hour = Counter()
        self._intent_counts = Counter()
        self._daily_usage = Counter()
        self._custom_habits: dict[str, dict[str, Any]] = {}

    async def observe(self, event: dict[str, Any]) -> None:
        ts = float(event.get("timestamp", time.time()))
        dt = datetime.fromtimestamp(ts)
        hour = int(event.get("hour", dt.hour))
        day = int(event.get("day", dt.weekday()))
        intent = str(event.get("intent", "")).strip().lower()

        self._events_by_hour[hour] += 1
        self._daily_usage[day] += 1
        if intent:
            self._intent_counts[intent] += 1

    async def update(self, state) -> list[dict[str, Any]]:
        """
        Evaluates scheduled habits against current state.
        Returns due habit actions (if any).
        """
        due_actions: list[dict[str, Any]] = []
        today = datetime.now().date().isoformat()
        for habit_id, habit in self._custom_habits.items():
            if habit.get("status") != "active":
                continue
            if state.hour != int(habit.get("trigger_hour", -1)):
                continue
            if state.day_of_week not in habit.get("trigger_days", []):
                continue

            # Once per day trigger protection.
            if habit.get("last_trigger_date") == today:
                continue

            habit["last_trigger_date"] = today
            habit["trigger_count"] = int(habit.get("trigger_count", 0)) + 1
            due_actions.append(
                {
                    "habit_id": habit_id,
                    "description": habit.get("description", ""),
                    "action": habit.get("action", "speak"),
                    "params": dict(habit.get("params", {})),
                }
            )

        if due_actions and hasattr(self.memory, "save_habits"):
            await self.memory.save_habits(self._custom_habits)
        return due_actions

    def add_habit(
        self,
        description: str,
        trigger_hour: int,
        trigger_days: list[int] | None = None,
        action: str = "speak",
        params: dict[str, Any] | None = None,
    ) -> str:
        habit_id = f"habit_{int(time.time() * 1000)}"
        self._custom_habits[habit_id] = {
            "id": habit_id,
            "description": description.strip(),
            "trigger_hour": int(trigger_hour),
            "trigger_days": list(trigger_days or list(range(7))),
            "action": action.strip() or "speak",
            "params": dict(params or {}),
            "status": "active",
            "trigger_count": 0,
            "last_trigger_date": "",
            "created_at": time.time(),
        }
        return habit_id

    def get_habits(self) -> list[dict[str, Any]]:
        return list(self._custom_habits.values())

    def get_daily_summary(self) -> dict[str, Any]:
        if self._daily_usage:
            active_days = sorted(self._daily_usage.items(), key=lambda x: x[1], reverse=True)
        else:
            active_days = []

        active_hours = sorted(self._events_by_hour.items(), key=lambda x: x[1], reverse=True)
        top_intents = self._intent_counts.most_common(10)

        # Simple streak: consecutive weekdays with any event count.
        # Keeps logic deterministic and lightweight.
        streak_days = 0
        today = datetime.now().weekday()
        for back in range(0, 7):
            d = (today - back) % 7
            if self._daily_usage.get(d, 0) > 0:
                streak_days += 1
            else:
                break

        return {
            "streak_days": streak_days,
            "top_intents": top_intents,
            "active_hours": [{"hour": h, "count": c} for h, c in active_hours[:6]],
            "active_days": [{"day": d, "count": c} for d, c in active_days[:7]],
            "custom_habits": len(self._custom_habits),
        }

