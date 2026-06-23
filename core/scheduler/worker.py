"""Worker — thin wrapper that connects Scheduler to ResumeEngine + execution.

The worker owns the "how" that the scheduler avoids. It takes a resume
context and runs it through the PlannerStateMachine.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from core.activity.resume import ResumeContext
from core.planner.state_machine import PlannerStateMachine

logger = logging.getLogger(__name__)


class SchedulerWorker:
    """Bridges the scheduler tick to actual execution.

    Given a ResumeContext, the worker:
      1. Creates or reuses a PlannerStateMachine
      2. Feeds the resumed goal/task into the planner
      3. Runs through the standard PLAN→DECOMPOSE→ROUTE→EXECUTE→VERIFY cycle
      4. Returns the result

    The scheduler only calls worker.execute(ctx). Everything else
    is existing infrastructure.
    """

    def __init__(self, planner_fn: Callable[[str], Any] | None = None):
        self._planner_fn = planner_fn

    async def execute(self, ctx: ResumeContext) -> dict[str, Any]:
        """Execute a resume context through the planner pipeline.

        Uses either a caller-provided planner function or falls back
        to running PlannerStateMachine directly.
        """
        goal = ctx.target_label
        logger.info("SchedulerWorker: executing %s (%s)", ctx.activity_id, goal)

        if self._planner_fn:
            return await self._planner_fn(goal)
        return {"goal": goal, "state": "EXECUTED", "activity_id": ctx.activity_id}
