"""Minimal strategy generator surface."""
from __future__ import annotations

from core.strategy.models import Prediction, Strategy


class StrategyGenerator:
    def generate(self, goal: str):
        return [Strategy(name="Default", description="Default implementation strategy", goal=goal, prediction=Prediction())]


def classify_goal(goal: str) -> str:
    return "coding" if any(token in goal.lower() for token in ("build", "fix", "code", "app")) else "general"


async def async_classify_goal(goal: str) -> str:
    return classify_goal(goal)
