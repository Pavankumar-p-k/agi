"""Scheduler — time-driven activity loop.

The scheduler is deliberately thin. It only decides WHAT to run next.
The HOW is delegated entirely to existing infrastructure:

    Scheduler → ResumeEngine → PlannerStateMachine → Agent Graph → Workflow Engine
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

logger = logging.getLogger(__name__)

DEFAULT_TICK_INTERVAL = 10.0  # seconds


class Scheduler:
    """Time-driven activity scheduler.

    On each tick:
      1. Refresh active activities (load + check deps + score)
      2. Pick the highest-scored ready activity
      3. Resume it through ResumeEngine + caller-provided execute_fn
      4. Sleep until the next tick

    No new planner, router, or workflow engine. Only delegation.
    """

    def __init__(
        self,
        activity_manager: ActivityManager,
        resume_engine: ResumeEngine,
        execute_fn: Callable[[str, str], Any] | None = None,
        policy: PriorityPolicy | None = None,
        tick_interval: float = DEFAULT_TICK_INTERVAL,
    ):
        self._mgr = activity_manager
        self._resume = resume_engine
        self._execute_fn = execute_fn
        self._queue = SchedulerQueue(activity_manager, policy=policy)
        self._tick_interval = tick_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._current_activity: ScheduledActivity | None = None
        self._ticks = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_activity(self) -> ScheduledActivity | None:
        return self._current_activity

    @property
    def queue(self) -> SchedulerQueue:
        return self._queue

    @property
    def ticks(self) -> int:
        return self._ticks

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the scheduler background loop. Idempotent."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Scheduler: started (tick_interval=%.1fs)", self._tick_interval)

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._current_activity = None
        logger.info("Scheduler: stopped")

    async def tick(self) -> None:
        """Execute one scheduler cycle. Exposed for testing or manual use."""
        self._ticks += 1
        logger.debug("Scheduler: tick=%d", self._ticks)

        # 1. Refresh activities
        ready = self._queue.refresh()
        if not ready:
            logger.debug("Scheduler: no ready activities")
            return

        # 2. Pick the best
        best = self._queue.get_best()
        if best is None:
            return

        self._current_activity = best

        # 3. Find resume point
        ctx = self._resume.find_resume_point(best.activity_id)
        if ctx is None:
            logger.warning("Scheduler: no resume point for %s", best.activity_id)
            self._current_activity = None
            return

        # 4. Mark as running
        self._queue.mark_running(best.activity_id)
        self._resume.mark_resumed(ctx)

        # 5. Execute (via caller callback or fallback)
        if self._execute_fn:
            try:
                await self._execute_fn(best.activity_id, ctx.target_label)
            except Exception as e:
                logger.error("Scheduler: execute failed for %s: %s",
                             best.activity_id, e)
                self._queue.mark_failed(best.activity_id)
        else:
            logger.info("Scheduler: no execute_fn — would resume %s (%r)",
                        best.activity_id, ctx.target_label)

        self._current_activity = None

    # ── Internal loop ──────────────────────────────────────────────────────

    async def _run(self) -> None:
        """Background tick loop."""
        try:
            while self._running:
                await self.tick()
                await asyncio.sleep(self._tick_interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Scheduler: loop crashed: %s", e, exc_info=True)
        finally:
            self._running = False
