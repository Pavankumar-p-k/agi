"""Scheduler — persistent, time-driven autonomous activity loop.

Architecture:
    Scheduler (this file)
        │
        ├── SchedulerQueue (dependency-aware + persistent)
        │       ├── SchedulerStore (SQLite)
        │       └── ActivityManager (ActivityGraph)
        │
        └── SchedulerRegistry (executor mapping)
                ├── ResearchExecutor → do_browser_research
                ├── BuildExecutor    → build_project
                └── ...
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable

from core.activity.manager import ActivityManager
from core.activity.resume import ResumeEngine
from core.scheduler.models import ScheduledActivity
from core.scheduler.policies import PriorityPolicy
from core.scheduler.queue import SchedulerQueue
from core.scheduler.registry import ExecutorFn, SchedulerRegistry
from core.scheduler.store import SchedulerStore

logger = logging.getLogger(__name__)

DEFAULT_TICK_INTERVAL = 10.0


class SchedulerState:
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class Scheduler:
    """Persistent, autonomous activity scheduler.

    On each tick:
      1. Refresh activities from store + ActivityGraph
      2. Pick the highest-scored ready activity
      3. Resolve an executor from the registry
      4. Execute it
      5. Mark as completed or failed

    State: stopped → running ↔ paused → stopped
    """

    def __init__(
        self,
        activity_manager: ActivityManager,
        resume_engine: ResumeEngine | None = None,
        execute_fn: Callable[[str, str], Any] | None = None,
        registry: SchedulerRegistry | None = None,
        store: SchedulerStore | None = None,
        policy: PriorityPolicy | None = None,
        tick_interval: float = DEFAULT_TICK_INTERVAL,
        store_db_path: str | None = None,
    ):
        self._mgr = activity_manager
        self._resume = resume_engine or ResumeEngine(activity_manager)
        self._execute_fn = execute_fn
        self._registry = registry or SchedulerRegistry()
        self._store = store or SchedulerStore(db_path=store_db_path)
        self._queue = SchedulerQueue(activity_manager, store=self._store, policy=policy)
        self._tick_interval = tick_interval
        self._state = SchedulerState.STOPPED
        self._task: asyncio.Task | None = None
        self._current_activity: ScheduledActivity | None = None
        self._ticks = 0
        self._on_tick: list[Callable[[dict[str, Any]], None]] = []

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == SchedulerState.RUNNING

    @property
    def is_paused(self) -> bool:
        return self._state == SchedulerState.PAUSED

    @property
    def current_activity(self) -> ScheduledActivity | None:
        return self._current_activity

    @property
    def queue(self) -> SchedulerQueue:
        return self._queue

    @property
    def ticks(self) -> int:
        return self._ticks

    @property
    def registry(self) -> SchedulerRegistry:
        return self._registry

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._state != SchedulerState.STOPPED:
            return
        self._state = SchedulerState.RUNNING
        self._task = asyncio.create_task(self._run())
        logger.info("Scheduler: started (tick_interval=%.1fs)", self._tick_interval)

    async def stop(self) -> None:
        self._state = SchedulerState.STOPPED
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._current_activity = None
        logger.info("Scheduler: stopped")

    async def pause(self) -> None:
        if self._state != SchedulerState.RUNNING:
            return
        self._state = SchedulerState.PAUSED
        logger.info("Scheduler: paused")

    async def resume(self) -> None:
        if self._state != SchedulerState.PAUSED:
            return
        self._state = SchedulerState.RUNNING
        logger.info("Scheduler: resumed")

    # ── Tick ─────────────────────────────────────────────────────────────────

    async def tick(self) -> dict[str, Any]:
        """Execute one scheduler cycle. Returns tick result metadata."""
        self._ticks += 1
        start = datetime.utcnow()
        result: dict[str, Any] = {
            "tick": self._ticks,
            "activity_id": None,
            "executed": False,
            "error": None,
            "duration_ms": 0,
        }
        _early_return = True

        try:
            # 1. Refresh activities
            ready = self._queue.refresh()
            if not ready:
                result["reason"] = "no_ready_activities"
                return result

            # 2. Pick the best
            best = self._queue.get_best()
            if best is None:
                result["reason"] = "no_best_activity"
                return result

            _early_return = False
            self._current_activity = best
            result["activity_id"] = best.activity_id

            # 3. Mark as running
            self._queue.mark_running(best.activity_id)

            # 4. Find resume point
            try:
                ctx = self._resume.find_resume_point(best.activity_id)
                if ctx:
                    self._resume.mark_resumed(ctx)
            except Exception as e:
                logger.debug("Scheduler: resume point lookup: %s", e)

            # 5. Execute (backward compat: execute_fn takes precedence)
            if self._execute_fn:
                try:
                    await self._execute_fn(best.activity_id, best.goal)
                    self._queue.mark_completed(best.activity_id)
                    result["executed"] = True
                    result["executor"] = "execute_fn"
                except Exception as e:
                    logger.error("Scheduler: execute_fn failed for %s: %s",
                                 best.activity_id, e)
                    self._queue.mark_failed(best.activity_id)
                    result["error"] = str(e)
            else:
                executor = self._resolve_executor(best)
                if executor is None:
                    logger.warning("Scheduler: no executor for %s (type=%s)",
                                   best.activity_id, best.node_type)
                    self._queue.mark_failed(best.activity_id)
                    result["error"] = f"no_executor_for_type:{best.node_type}"
                    return result
                try:
                    exec_result = await executor(
                        activity_id=best.activity_id,
                        goal=best.goal,
                        metadata=best.metadata,
                    )
                    self._queue.mark_completed(best.activity_id)
                    result["executed"] = True
                    result["executor"] = executor.__name__ if hasattr(executor, "__name__") else str(executor)
                    result["result"] = exec_result
                except Exception as e:
                    logger.error("Scheduler: execution failed for %s: %s",
                                 best.activity_id, e)
                    self._queue.mark_failed(best.activity_id)
                    result["error"] = str(e)

            return result
        finally:
            duration = (datetime.utcnow() - start).total_seconds() * 1000
            result["duration_ms"] = round(duration, 1)
            self._fire_tick_callbacks(result)
            if not _early_return:
                self._current_activity = None

    def _resolve_executor(self, act: ScheduledActivity) -> ExecutorFn | None:
        """Pick the right executor for an activity.

        Resolution order:
          1. node_type match in registry
          2. metadata.get("tool_type") match in registry
          3. metadata.get("executor") match in registry
        """
        for key in (act.node_type,
                    act.metadata.get("tool_type", ""),
                    act.metadata.get("executor", "")):
            if key:
                executor = self._registry.get(key)
                if executor:
                    return executor
        return None

    # ── Tick callbacks ──────────────────────────────────────────────────────

    def on_tick(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback fired after each tick with the tick result."""
        self._on_tick.append(callback)

    def _fire_tick_callbacks(self, result: dict[str, Any]) -> None:
        for cb in self._on_tick:
            try:
                cb(result)
            except Exception as e:
                logger.warning("Scheduler: tick callback error: %s", e)

    # ── Internal loop ───────────────────────────────────────────────────────

    async def _run(self) -> None:
        try:
            while self._state != SchedulerState.STOPPED:
                if self._state == SchedulerState.RUNNING:
                    await self.tick()
                await asyncio.sleep(self._tick_interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Scheduler: loop crashed: %s", e, exc_info=True)
        finally:
            if self._state != SchedulerState.STOPPED:
                self._state = SchedulerState.STOPPED
