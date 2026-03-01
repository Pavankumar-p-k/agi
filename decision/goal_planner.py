from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class PlannedDecision:
    action: str
    tool: str
    params: dict[str, Any]
    reasoning: str
    confidence: float
    priority: int
    autonomous: bool = True
    goal_id: str = ""


class GoalPlanner:
    """
    Turns predictions and goal steps into executable decisions.
    """

    def __init__(self, memory):
        self.memory = memory
        self._dnd_enabled = False
        self._dnd_hours: set[int] = set()

    def set_dnd(self, enabled: bool, hours: list[int] | None = None) -> None:
        self._dnd_enabled = bool(enabled)
        self._dnd_hours = {int(h) % 24 for h in (hours or [])}

    async def make_decision(self, prediction: dict[str, Any], state, history: list[dict[str, Any]]) -> PlannedDecision | None:
        action = str(prediction.get("action", "")).strip()
        tool = str(prediction.get("tool", "")).strip()
        if not action or not tool:
            return None

        if self._dnd_enabled and state.hour in self._dnd_hours:
            if str(prediction.get("type", "")).lower() != "alert":
                return None

        confidence = float(prediction.get("confidence", 0.0))
        if confidence <= 0:
            return None

        # Avoid repeating same action too frequently if it already succeeded.
        now = time.time()
        for item in reversed(history[-15:]):
            if item.get("action") == action and item.get("success") is True:
                age = now - float(item.get("timestamp", now))
                if age < 20 * 60:
                    return None
                break

        ptype = str(prediction.get("type", "")).lower()
        priority = 3
        if ptype == "alert":
            priority = 1
        elif ptype == "scheduled":
            priority = 2
        elif confidence >= 0.8:
            priority = 2

        reasoning = str(prediction.get("reason", "Predicted user need")).strip()
        params = dict(prediction.get("params", {}))
        return PlannedDecision(
            action=action,
            tool=tool,
            params=params,
            reasoning=reasoning,
            confidence=round(confidence, 3),
            priority=priority,
            autonomous=True,
        )

    async def step_to_decision(self, step: dict[str, Any], goal, state) -> PlannedDecision | None:
        action = str(step.get("action", "")).strip() or f"goal_step_{goal.current_step + 1}"
        tool = str(step.get("tool", "")).strip() or "brain"
        params = dict(step.get("params", {}))
        desc = str(step.get("description", "")).strip()
        step_num = int(step.get("step_num", goal.current_step + 1))
        total = max(1, len(goal.steps))
        confidence = 0.9 if step_num == 1 else 0.82
        reasoning = f"Goal '{goal.description}' step {step_num}/{total}: {desc or action}"

        if self._dnd_enabled and state.hour in self._dnd_hours and tool == "speak":
            return None

        return PlannedDecision(
            action=action,
            tool=tool,
            params=params,
            reasoning=reasoning,
            confidence=confidence,
            priority=2,
            autonomous=True,
            goal_id=goal.id,
        )

