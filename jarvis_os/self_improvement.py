"""Self-improvement loop for the JARVIS AI Operating System."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Dict, Optional

logger = logging.getLogger("jarvis.os.self_improvement")


class SelfImprovementLoop:
    def __init__(self, world_model: Any, learning: Any, observability: Any, config: Optional[dict] = None):
        self.world_model = world_model
        self.learning = learning
        self.observability = observability
        self.config = config or {}
        self._tool_stats = defaultdict(lambda: {"success": 0, "failure": 0})
        self._running = False
        self._last_reflection: Dict[str, Any] = {}
        self._task: Optional[asyncio.Task] = None

    async def initialize(self):
        if self._running:
            return
        self._running = True
        interval = int(self.config.get("reflection_interval_s", 300))
        self._task = asyncio.create_task(self._background_loop(interval))

    async def shutdown(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def capture(self, goal: Any, plan: Any, execution_report: Any, reflection: Dict[str, Any]) -> Dict[str, Any]:
        for step in execution_report.step_results:
            bucket = self._tool_stats[step.tool]
            if step.success:
                bucket["success"] += 1
            else:
                bucket["failure"] += 1
        snapshot = self.status()
        snapshot["goal_id"] = goal.goal_id
        snapshot["plan_id"] = plan.plan_id
        snapshot["execution_id"] = execution_report.execution_id
        snapshot["reflection"] = reflection
        self._last_reflection = snapshot
        await self.world_model.observe(
            {
                "type": "self_improvement",
                "goal_id": goal.goal_id,
                "plan_id": plan.plan_id,
                "execution_id": execution_report.execution_id,
                "snapshot": snapshot,
            }
        )
        self.observability.record_event("self_improvement.capture", snapshot)
        return snapshot

    def status(self) -> Dict[str, Any]:
        ranked = []
        for tool, stats in self._tool_stats.items():
            total = stats["success"] + stats["failure"]
            ranked.append(
                {
                    "tool": tool,
                    "success": stats["success"],
                    "failure": stats["failure"],
                    "success_rate": round(stats["success"] / total, 3) if total else 0.0,
                }
            )
        ranked.sort(key=lambda item: item["success_rate"], reverse=True)
        return {
            "running": self._running,
            "tracked_tools": ranked,
            "last_reflection": self._last_reflection,
            "timestamp": time.time(),
        }

    async def _background_loop(self, interval_s: int):
        while self._running:
            try:
                if self._tool_stats:
                    insights = self.status()
                    await self.learning.record_feedback(
                        skill="runtime_execution",
                        score=insights["tracked_tools"][0]["success_rate"] if insights["tracked_tools"] else 0.0,
                        notes="Automated reflection on tool execution quality.",
                    )
                    self.observability.record_event("self_improvement.background_reflection", insights)
            except Exception as exc:
                logger.debug("Self-improvement reflection skipped: %s", exc)
            await asyncio.sleep(interval_s)
