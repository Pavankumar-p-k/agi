from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.planner.unified_store import UnifiedStore
from memory.memory_facade import memory as _memory_facade
from brain.events.event_bus import Event, global_event_bus
from brain.events.event_types import LearningApplied

logger = logging.getLogger(__name__)


@dataclass
class ImprovementMetric:
    """Metrics measured before and after a learning intervention."""
    before_success_rate: float = 0.0
    after_success_rate: float = 0.0
    before_avg_duration_ms: float = 0.0
    after_avg_duration_ms: float = 0.0
    sample_count: int = 0


class SelfImprovementEngine:
    """Recursive self-improvement with A/B testing and auto-revert.

    Flow:
        1. Take a baseline measurement of current performance
        2. Apply learned lessons (modify planner prompts, suppress actions)
        3. Measure performance after intervention
        4. If improved → keep the change
        5. If degraded → revert the change
        6. Store the outcome as a meta-lesson

    This creates a positive feedback loop where the system learns
    not just from task outcomes but from the effectiveness of its
    own learning process.
    """

    def __init__(self, memory_manager=None,
                 goal_manager: UnifiedStore | None = None):
        self.memory = memory_manager or _memory_facade
        self.goals = goal_manager
        self._change_log: list[dict] = []
        self._active_interventions: dict[str, dict] = {}
        self._rollback_stack: deque[dict] = deque(maxlen=100)

    async def propose_intervention(self, name: str, description: str,
                                   intervention_fn: Any,
                                   rollback_fn: Any | None = None) -> str:
        """Propose a behavioral change to be A/B tested.

        Args:
            name: Short name for the intervention
            description: What it does
            intervention_fn: async callable to apply the change
            rollback_fn: async callable to revert the change

        Returns:
            intervention_id
        """
        intervention_id = str(uuid.uuid4())
        self._active_interventions[intervention_id] = {
            "id": intervention_id,
            "name": name,
            "description": description,
            "intervention_fn": intervention_fn,
            "rollback_fn": rollback_fn,
            "baseline": None,
            "outcome": None,
            "status": "proposed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return intervention_id

    async def measure_baseline(self, n_samples: int = 10) -> dict:
        """Take a baseline measurement of current performance.

        Reads recent task traces from TaskMemory and computes
        success rate and average duration.
        """
        traces = self.memory.get_recent_traces(limit=n_samples, user_id="brain")
        if not traces:
            return {"success_rate": 0.0, "avg_duration_ms": 0.0, "samples": 0}

        successes = sum(1 for t in traces if t.get("success"))
        durations = [t.get("duration_ms", 0) for t in traces if t.get("duration_ms", 0) > 0]

        return {
            "success_rate": successes / len(traces) if traces else 0.0,
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0.0,
            "samples": len(traces),
        }

    async def apply_and_test(self, intervention_id: str,
                             evaluation_samples: int = 20) -> dict:
        """Apply an intervention, measure impact, and keep or revert.

        Returns the outcome: kept, reverted, or failed.
        """
        intervention = self._active_interventions.get(intervention_id)
        if not intervention:
            return {"status": "error", "error": "Intervention not found"}

        # 1. Measure baseline
        baseline = await self.measure_baseline(evaluation_samples)
        intervention["baseline"] = baseline
        logger.info("[SelfImprovement] baseline for '%s': success=%.1f%% avg_dur=%.0fms",
                    intervention["name"],
                    baseline["success_rate"] * 100,
                    baseline["avg_duration_ms"])

        # 2. Apply the change
        try:
            fn = intervention["intervention_fn"]
            if fn:
                if callable(fn):
                    result = fn() if not asyncio.iscoroutinefunction(fn) else await fn()
                intervention["status"] = "applied"
                self._rollback_stack.append({
                    "intervention_id": intervention_id,
                    "rollback_fn": intervention["rollback_fn"],
                    "applied_at": datetime.now(timezone.utc).isoformat(),
                })
                logger.info("[SelfImprovement] applied: %s", intervention["name"])
        except Exception as e:
            logger.exception("[SelfImprovement] apply failed: %s", e)
            intervention["status"] = "failed"
            return {"status": "failed", "error": str(e)}

        # 3. Wait for samples to accumulate, then measure
        await asyncio.sleep(0.5)

        # Collect post-intervention traces
        after = await self.measure_baseline(evaluation_samples)

        # 4. Compare and decide
        metric = ImprovementMetric(
            before_success_rate=baseline["success_rate"],
            after_success_rate=after["success_rate"],
            before_avg_duration_ms=baseline["avg_duration_ms"],
            after_avg_duration_ms=after["avg_duration_ms"],
            sample_count=after["samples"],
        )

        improvement = (metric.after_success_rate - metric.before_success_rate)
        speed_change = metric.before_avg_duration_ms - metric.after_avg_duration_ms

        outcome = "kept" if improvement >= 0 else "reverted"
        intervention["outcome"] = outcome

        # 5. Revert if worse
        if outcome == "reverted" and intervention["rollback_fn"]:
            try:
                rfn = intervention["rollback_fn"]
                if callable(rfn):
                    rfn() if not asyncio.iscoroutinefunction(rfn) else await rfn()
                logger.info("[SelfImprovement] reverted: %s (success dropped %.0f%%)",
                            intervention["name"], improvement * -100)
            except Exception as e:
                logger.exception("[SelfImprovement] rollback failed: %s", e)

        # 6. Store meta-lesson
        self.memory.store_decision(
            context=f"Self-improvement intervention: {intervention['name']}",
            decision=f"{'Keep' if outcome == 'kept' else 'Revert'} intervention",
            outcome=f"Success rate: {metric.before_success_rate:.0%} -> {metric.after_success_rate:.0%}",
            lesson=(
                f"Intervention '{intervention['name']}' was {outcome}. "
                f"Success rate {'improved' if improvement >= 0 else 'dropped'} by {abs(improvement):.0%}. "
                f"{'Faster' if speed_change > 0 else 'Slower'} by {abs(speed_change):.0f}ms."
            ),
            success=(outcome == "kept"),
            tags=["self_improvement", "meta_learning", outcome],
            user_id="brain",
        )

        await global_event_bus.publish(Event(
            type="learning.applied",
            source="self_improvement",
            payload=LearningApplied(
                lesson_count=1,
                affected_subsystems=["planning", "execution"],
            ).__dict__,
        ))

        self._change_log.append({
            "id": intervention_id,
            "name": intervention["name"],
            "outcome": outcome,
            "baseline": baseline,
            "after": after,
            "improvement": round(improvement, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "completed",
            "outcome": outcome,
            "metric": {
                "before_success_rate": round(metric.before_success_rate, 3),
                "after_success_rate": round(metric.after_success_rate, 3),
                "before_avg_duration_ms": round(metric.before_avg_duration_ms, 1),
                "after_avg_duration_ms": round(metric.after_avg_duration_ms, 1),
                "improvement": round(improvement, 3),
            },
        }

    def get_change_log(self, limit: int = 20) -> list[dict]:
        return list(self._change_log)[-limit:]

    def get_stats(self) -> dict:
        kept = sum(1 for c in self._change_log if c["outcome"] == "kept")
        reverted = sum(1 for c in self._change_log if c["outcome"] == "reverted")
        return {
            "total_interventions": len(self._change_log),
            "kept": kept,
            "reverted": reverted,
            "active": len(self._active_interventions),
            "improvement_rate": kept / (kept + reverted) if (kept + reverted) > 0 else 0,
        }


import asyncio
