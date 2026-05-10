# decision/goal_planner.py
from __future__ import annotations

from typing import Optional


class GoalPlanner:
    def __init__(self, memory) -> None:
        self.memory = memory

    async def make_decision(self, prediction: dict, state, history: list) -> Optional[object]:
        # Convert a prediction into an AGI decision object
        try:
            from core.agi_core import AGIDecision

            return AGIDecision(
                action=prediction.get("action", ""),
                tool=prediction.get("tool", ""),
                params=prediction.get("params", {}),
                reasoning=prediction.get("reason", ""),
                confidence=prediction.get("confidence", 0.5),
                priority=prediction.get("priority", 3),
                autonomous=True,
            )
        except Exception:
            return None
