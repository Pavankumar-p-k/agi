"""Scheduler — persistent, time-driven autonomous activity loop with worker pool.

Architecture:
    Scheduler (this file)
        │
        ├── SchedulerQueue (dependency-aware + persistent)
        │       ├── SchedulerStore (SQLite)
        │       └── ActivityManager (ActivityGraph)
        │
        ├── Worker Pool (concurrent execution, max_workers=N)
        │       └── asyncio.Task per activity
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
from core.scheduler.intelligence import ActivityIntelligence
from core.scheduler.models import ScheduledActivity
from core.scheduler.policies import PriorityPolicy
from core.scheduler.queue import SchedulerQueue
from core.scheduler.registry import ExecutorFn, SchedulerRegistry
from core.scheduler.store import SchedulerStore

logger = logging.getLogger(__name__)

DEFAULT_TICK_INTERVAL = 10.0
DEFAULT_MAX_WORKERS = 3


class SchedulerState:
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class Scheduler:
    """Persistent, autonomous activity scheduler with concurrent worker pool.

    On each tick:
      1. Refresh activities from store + ActivityGraph
      2. Clean up finished workers
      3. Fill available worker slots with best-scored ready activities
      4. Launch each activity as an async worker task

    State: stopped → running ↔ paused → stopped
    """

    def __init__(
        self,
        activity_manager: ActivityManager | None = None,
        resume_engine: ResumeEngine | None = None,
        execute_fn: Callable[[str, str], Any] | None = None,
        registry: SchedulerRegistry | None = None,
        store: SchedulerStore | None = None,
        policy: PriorityPolicy | None = None,
        intelligence: ActivityIntelligence | None = None,
        tick_interval: float = DEFAULT_TICK_INTERVAL,
        max_workers: int = DEFAULT_MAX_WORKERS,
        store_db_path: str | None = None,
    ):
        self._mgr = activity_manager or ActivityManager()
        self._resume = resume_engine or ResumeEngine(self._mgr)
        self._execute_fn = execute_fn
        self._registry = registry or SchedulerRegistry()
        self._store = store or SchedulerStore(db_path=store_db_path)
        self._intelligence = intelligence or ActivityIntelligence(db_path=store_db_path)
        self._queue = SchedulerQueue(self._mgr, store=self._store, policy=policy)
        self._tick_interval = tick_interval
        self._max_workers = max_workers
        self._state = SchedulerState.STOPPED
        self._task: asyncio.Task | None = None
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._running_start_times: dict[str, datetime] = {}
        self._current_activity: ScheduledActivity | None = None
        self._ticks = 0
        self._on_tick: list[Callable[[dict[str, Any]], None]] = []

        # Wire intelligence into policy if it doesn't have one
        if policy and not policy.intelligence:
            policy.intelligence = self._intelligence

    @property
    def intelligence(self) -> ActivityIntelligence:
        return self._intelligence

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

    @property
    def running_count(self) -> int:
        """Number of currently executing worker tasks."""
        return len(self._running_tasks)

    @property
    def running_activities(self) -> list[str]:
        """Activity IDs of currently executing workers."""
        return list(self._running_tasks.keys())

    @property
    def max_workers(self) -> int:
        return self._max_workers

    @max_workers.setter
    def max_workers(self, n: int) -> None:
        if n < 1:
            raise ValueError("max_workers must be >= 1")
        self._max_workers = n

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._state != SchedulerState.STOPPED:
            return
        self._state = SchedulerState.RUNNING
        self._task = asyncio.create_task(self._run())
        logger.info("Scheduler: started (tick_interval=%.1fs, max_workers=%d)",
                     self._tick_interval, self._max_workers)

    async def stop(self) -> None:
        self._state = SchedulerState.STOPPED
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        # Cancel all running workers
        if self._running_tasks:
            for aid, t in self._running_tasks.items():
                t.cancel()
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)
            self._running_tasks.clear()
        self._current_activity = None
        logger.info("Scheduler: stopped")

    async def pause(self) -> None:
        if self._state != SchedulerState.RUNNING:
            return
        self._state = SchedulerState.PAUSED
        logger.info("Scheduler: paused (%d worker(s) continue running)",
                     self.running_count)

    async def resume(self) -> None:
        if self._state != SchedulerState.PAUSED:
            return
        self._state = SchedulerState.RUNNING
        logger.info("Scheduler: resumed")

    # ── Tick ─────────────────────────────────────────────────────────────────

    async def tick(self) -> dict[str, Any]:
        """Execute one scheduler cycle. Fill worker slots with ready activities.

        Returns tick result metadata including which activities were launched.
        """
        self._ticks += 1
        start = datetime.utcnow()
        result: dict[str, Any] = {
            "tick": self._ticks,
            "activity_id": None,
            "executed": False,
            "launched": [],
            "error": None,
            "duration_ms": 0,
            "running_count": 0,
        }

        try:
            # 1. Refresh activities
            self._queue.refresh()

            # 2. Clean up finished workers
            self._cleanup_workers()
            result["running_count"] = self.running_count

            # 3. Fill available worker slots
            available = self._max_workers - self.running_count
            if available <= 0:
                result["reason"] = "all_workers_busy"
                return result

            # 4. Pick best N activities (chain-aware for parallelism)
            running_ids = set(self._running_tasks.keys())
            best_n = self._queue.get_best_n_chain_aware(available, exclude=running_ids)
            if not best_n:
                result["reason"] = "no_ready_activities"
                return result

            # 5. Pre-check executors — fail fast for unresolvable activities
            to_launch: list[ScheduledActivity] = []
            for act in best_n:
                if not self._execute_fn and not self._resolve_executor(act):
                    logger.warning("Scheduler: no executor for %s (type=%s)",
                                   act.activity_id, act.node_type)
                    self._queue.mark_failed(act.activity_id)
                    result["error"] = f"no_executor_for_type:{act.node_type}"
                else:
                    to_launch.append(act)

            if not to_launch:
                result["reason"] = "no_resolvable_activities"
                return result

            # 6. Launch workers for pre-validated activities
            launched = []
            for act in to_launch:
                self._queue.mark_running(act.activity_id)
                task = asyncio.create_task(self._run_worker(act))
                self._running_tasks[act.activity_id] = task
                launched.append(act.activity_id)

            self._current_activity = best_n[0]
            result["activity_id"] = best_n[0].activity_id
            result["executed"] = True
            result["launched"] = launched
            result["running_count"] = self.running_count

            return result
        finally:
            duration = (datetime.utcnow() - start).total_seconds() * 1000
            result["duration_ms"] = round(duration, 1)
            self._fire_tick_callbacks(result)

    # ── Worker pool ──────────────────────────────────────────────────────────

    async def _run_worker(self, activity: ScheduledActivity) -> None:
        """Execute a single activity in a background worker task.

        Handles resume point lookup, executor resolution, status updates,
        prediction recording, calibration, and cleanup.
        """
        aid = activity.activity_id
        start_time = datetime.utcnow()
        self._running_start_times[aid] = start_time
        success = False

        # Phase 8.3B: predict before execution
        prediction = self._intelligence.predict(activity.node_type)
        pred_success = prediction.success_probability if prediction.confidence > 0 else None
        pred_dur = int(prediction.expected_duration_ms) if prediction.confidence > 0 else None
        pred_source = prediction.prediction_source if prediction.confidence > 0 else None

        try:
            # Find resume point
            try:
                ctx = self._resume.find_resume_point(aid)
                if ctx:
                    self._resume.mark_resumed(ctx)
            except Exception as e:
                logger.debug("Scheduler: resume point lookup for %s: %s", aid, e)

            # Execute (backward compat: execute_fn takes precedence)
            if self._execute_fn:
                await self._execute_fn(aid, activity.goal)
                self._queue.mark_completed(aid)
                success = True
            else:
                executor = self._resolve_executor(activity)
                if executor is None:
                    logger.warning("Scheduler: no executor for %s (type=%s)",
                                   aid, activity.node_type)
                    self._queue.mark_failed(aid)
                    return
                await executor(
                    activity_id=aid,
                    goal=activity.goal,
                    metadata=activity.metadata,
                )
                self._queue.mark_completed(aid)
                success = True
        except asyncio.CancelledError:
            logger.info("Scheduler: worker %s cancelled", aid)
            self._running_start_times.pop(aid, None)
            raise
        except Exception as e:
            logger.error("Scheduler: worker %s failed: %s", aid, e)
            self._queue.mark_failed(aid)
            success = False
        finally:
            # Phase 8.3B: record outcome + prediction for calibration
            duration_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )
            try:
                self._intelligence.record(
                    activity_id=aid,
                    node_type=activity.node_type,
                    duration_ms=max(duration_ms, 1),
                    success=success,
                    goal=activity.goal,
                    metadata=activity.metadata,
                    predicted_success=pred_success,
                    predicted_duration_ms=pred_dur,
                    prediction_source=pred_source,
                )
            except Exception as e:
                logger.warning("Scheduler: intelligence record error: %s", e)
            self._running_tasks.pop(aid, None)
            self._running_start_times.pop(aid, None)

    def _cleanup_workers(self) -> None:
        """Remove finished/cancelled workers from the running tracking dict."""
        done = [aid for aid, t in self._running_tasks.items() if t.done()]
        for aid in done:
            exc = self._running_tasks[aid].exception()
            if exc and not isinstance(exc, asyncio.CancelledError):
                logger.warning("Scheduler: worker %s raised: %s", aid, exc)
            self._running_tasks.pop(aid, None)

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
