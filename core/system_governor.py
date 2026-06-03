"""core/system_governor.py
Phase 4 (D1): System Governor — now with real governance.

Integrates:
  - TaskRouter   → intelligent task routing
  - ResourceMonitor → CPU/RAM/disk awareness
  - WorkQueue    → async priority queue with persistence

Original retry/replan/abort logic is preserved as GovernorDecision
for backward-compatibility with existing callers.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ── backward-compatible GovernorDecision (kept for existing callers) ──────────

@dataclass
class GovernorDecision:
    action: str  # "retry", "replan", "abort", "switch_tool", "escalate", "pause"
    reason: str
    confidence: float = 0.5
    suggested_agent: str = ""
    details: str = ""


# ── main class ────────────────────────────────────────────────────────────────

class SystemGovernor:
    """Central authority for task routing, resource governance, and retry logic.

    New API
    -------
    governor.submit(task, priority)   — enqueue a task
    governor.get_status()             — queue stats + resource snapshot
    governor.route(task)              — dry-run routing (async)

    Legacy API (unchanged)
    ----------------------
    governor.decide(...)              — retry/replan/abort decisions
    governor.get_history(project)     — decision history
    governor.reset(project)           — clear history
    """

    def __init__(self):
        # Legacy decision history
        self.history: dict[str, list[GovernorDecision]] = {}

        # Lazy-loaded governance components
        self._router   = None
        self._monitor  = None
        self._queue    = None

    # ── governance components (lazy init) ─────────────────────────────────────

    @property
    def router(self):
        if self._router is None:
            from core.governance.task_router import task_router
            self._router = task_router
        return self._router

    @property
    def monitor(self):
        if self._monitor is None:
            from core.governance.resource_monitor import resource_monitor
            self._monitor = resource_monitor
        return self._monitor

    @property
    def queue(self):
        if self._queue is None:
            from core.governance.work_queue import work_queue
            self._queue = work_queue
        return self._queue

    # ── new governance API ────────────────────────────────────────────────────

    async def submit(self, task: str, priority: int = 5, context: dict | None = None) -> str:
        """Submit a task to the work queue. Returns task_id."""
        return await self.queue.enqueue(task, priority=priority, context=context or {})

    def get_status(self) -> dict:
        """Return combined queue stats + resource snapshot."""
        queue_status    = self.queue.get_status()
        resource_snap   = self.monitor.get_snapshot()
        return {
            "queue":     queue_status,
            "resources": resource_snap.to_dict(),
        }

    async def route(self, task: str, context: dict | None = None):
        """Dry-run routing — returns a RouteDecision without executing."""
        return await self.router.route(task, context or {})

    def start_queue(self) -> None:
        """Start the background work queue loop (call at app startup)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self.queue.start()
            else:
                logger.warning("[SystemGovernor] No running event loop — queue not started.")
        except RuntimeError:
            logger.warning("[SystemGovernor] Could not start queue loop.")

    # ── legacy API (preserved for backward-compatibility) ─────────────────────

    def decide(
        self,
        project: str,
        failures: list[str],
        failure_category: str,
        retries: int,
        max_retries: int,
        budget_remaining: float,
        quality_score: Optional[float] = None,
        score_trend: str = "stable",
        partial_progress: Optional[dict] = None,
        has_usable_outputs: bool = False,
    ) -> GovernorDecision:
        self.history.setdefault(project, [])

        # Check resource constraints first
        if self.monitor.should_reject():
            return self._record(project, GovernorDecision(
                action="pause", reason="System critically overloaded — pausing",
                confidence=0.9,
            ))

        if retries >= max_retries:
            return self._record(project, GovernorDecision(
                action="abort", reason="Max retries reached", confidence=1.0,
                details=f"{retries}/{max_retries}",
            ))

        if budget_remaining < 0.1:
            return self._record(project, GovernorDecision(
                action="abort", reason="Budget exhausted", confidence=1.0,
            ))

        if (retries >= 2 and quality_score is not None
                and score_trend == "declining" and has_usable_outputs):
            return self._record(project, GovernorDecision(
                action="escalate",
                reason="Quality declining but usable outputs exist",
                confidence=0.7, details=f"score={quality_score:.1f}",
            ))

        if failure_category == "TOOL" and retries >= 1:
            return self._record(project, GovernorDecision(
                action="switch_tool",
                reason=f"Tool failed {retries + 1} times", confidence=0.8,
            ))

        if failure_category == "LOGIC":
            if retries >= 1:
                return self._record(project, GovernorDecision(
                    action="replan", reason="Logic failure persists",
                    confidence=0.75,
                    details=failures[0][:100] if failures else "",
                ))
            return self._record(project, GovernorDecision(
                action="retry", reason="First logic failure, retrying",
                confidence=0.6,
            ))

        if failure_category == "UNKNOWN" and retries >= 2:
            return self._record(project, GovernorDecision(
                action="pause",
                reason="Unknown failure pattern, pausing for review",
                confidence=0.5,
            ))

        return self._record(project, GovernorDecision(
            action="retry", reason="Default retry",
            confidence=0.5, details=failure_category,
        ))

    def _record(self, project: str, d: GovernorDecision) -> GovernorDecision:
        self.history[project].append(d)
        logger.info("[GOVERNOR] %s: %s (%.1f) — %s", project, d.action, d.confidence, d.reason)
        return d

    def get_history(self, project: str) -> list[GovernorDecision]:
        return self.history.get(project, [])

    def reset(self, project: str) -> None:
        self.history.pop(project, None)


# ── singleton ─────────────────────────────────────────────────────────────────

system_governor = SystemGovernor()
