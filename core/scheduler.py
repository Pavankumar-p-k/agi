"""core/scheduler.py
Recurring automated tasks — like Cowork's scheduled tasks.
Supports daily@HH:MM, weekly@day@HH:MM, hourly schedules.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Callable

logger = logging.getLogger("scheduler")

TASKS_DB = "data/scheduler_tasks.json"


class JarvisScheduler:
    """Recurring automated tasks with persistent storage."""

    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self._handlers: dict[str, Callable] = {}
        self._loop_task: Optional[asyncio.Task] = None
        self._load_tasks()

    def register_handler(self, task_type: str, handler: Callable):
        """Register an async handler for a task type."""
        self._handlers[task_type] = handler

    def add_task(self, task_id: str, schedule: str, action: dict):
        """
        schedule: "daily@09:00" | "weekly@monday@09:00" | "hourly"
        action: {type: "morning_digest"|"file_task"|"custom", params: {}}
        """
        self.tasks[task_id] = {
            "schedule": schedule,
            "action": action,
            "enabled": True,
            "last_run": None,
        }
        self._persist_tasks()
        logger.info(f"[SCHEDULER] Task '{task_id}' added: {schedule}")

    def remove_task(self, task_id: str):
        self.tasks.pop(task_id, None)
        self._persist_tasks()

    def get_tasks(self) -> dict:
        return dict(self.tasks)

    async def start(self):
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._run_loop())
            logger.info("[SCHEDULER] Started background loop")

    async def stop(self):
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
            logger.info("[SCHEDULER] Stopped")

    async def _run_loop(self):
        while True:
            try:
                await self._check_due()
            except Exception as e:
                logger.warning(f"[SCHEDULER] Loop error: {e}")
            await asyncio.sleep(60)

    async def _check_due(self):
        now = datetime.now()
        for task_id, task in list(self.tasks.items()):
            if not task["enabled"]:
                continue
            if self._is_due(task, now):
                logger.info(f"[SCHEDULER] Running task '{task_id}'")
                await self._execute_task(task)
                task["last_run"] = now.isoformat()
                self._persist_tasks()

    def _is_due(self, task: dict, now: datetime) -> bool:
        schedule = task["schedule"]
        last_run = task.get("last_run")
        if schedule == "hourly":
            if last_run:
                last = datetime.fromisoformat(last_run)
                if (now - last).total_seconds() < 3600:
                    return False
            return True

        if schedule.startswith("daily@"):
            time_str = schedule.split("@")[1]
            target = now.replace(hour=int(time_str.split(":")[0]), minute=int(time_str.split(":")[1]), second=0, microsecond=0)
            if last_run:
                last = datetime.fromisoformat(last_run)
                if last.date() == now.date():
                    return False
            return now >= target and (now - target).total_seconds() < 120

        if schedule.startswith("weekly@"):
            parts = schedule.split("@")
            day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
            target_day = day_map.get(parts[1].lower(), now.weekday())
            time_str = parts[2] if len(parts) > 2 else "09:00"
            if now.weekday() != target_day:
                return False
            target = now.replace(hour=int(time_str.split(":")[0]), minute=int(time_str.split(":")[1]), second=0, microsecond=0)
            if last_run:
                last = datetime.fromisoformat(last_run)
                if last.date() == now.date():
                    return False
            return now >= target and (now - target).total_seconds() < 120

        return False

    async def _execute_task(self, task: dict):
        action = task.get("action", {})
        task_type = action.get("type", "custom")
        handler = self._handlers.get(task_type)
        if handler:
            try:
                await handler(action.get("params", {}))
            except Exception as e:
                logger.error(f"[SCHEDULER] Handler '{task_type}' failed: {e}")
        else:
            logger.warning(f"[SCHEDULER] No handler for task type '{task_type}'")

    def _persist_tasks(self):
        try:
            os.makedirs(os.path.dirname(TASKS_DB) or ".", exist_ok=True)
            with open(TASKS_DB, "w") as f:
                json.dump(self.tasks, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"[SCHEDULER] Persist failed: {e}")

    def _load_tasks(self):
        try:
            if os.path.exists(TASKS_DB):
                with open(TASKS_DB, "r") as f:
                    self.tasks = json.load(f)
        except Exception as e:
            logger.warning(f"[SCHEDULER] Load failed: {e}")


scheduler = JarvisScheduler()
