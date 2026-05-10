from __future__ import annotations

from typing import Any


class MetaController:
    def __init__(self, max_iterations: int = 5) -> None:
        self.max_iterations = max_iterations

    def decide(self, iteration: int, evaluation: dict[str, Any]) -> dict[str, Any]:
        if iteration >= self.max_iterations:
            return {"action": "stop", "reason": "Max iterations reached"}

        score = evaluation.get("score", 0.0)
        replan = evaluation.get("replan", True)

        if score >= 0.8:
            return {"action": "stop", "reason": "Success threshold met"}

        if replan:
            return {"action": "replan", "reason": "Evaluation indicates replanning needed"}

        return {"action": "continue", "reason": "Continue with current plan"}