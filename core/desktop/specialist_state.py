"""DesktopLocalState — what the desktop specialist currently knows.

Tracks the open task, accumulated observations, and a structured
execution history. Recording a result closes the current task.
"""
from __future__ import annotations

from typing import Any, Optional


class DesktopLocalState:
    """Local, in-memory state for the desktop specialist."""

    def __init__(self) -> None:
        self.current_task: Optional[dict] = None
        self.observations: list = []
        self.execution_history: list = []

    def begin_task(self, request_id: str, goal: str) -> None:
        self.current_task = {"request_id": str(request_id), "goal": str(goal)}

    def record_observation(self, observation: Any) -> None:
        self.observations.append(observation)

    def record_result(self, result) -> None:
        """Record a DesktopExecutionResult and close the open task."""
        self.execution_history.append({
            "request_id": getattr(result, "request_id", ""),
            "status": getattr(getattr(result, "status", None), "value",
                              str(getattr(result, "status", ""))),
            "observations": list(getattr(result, "observations", [])),
            "actions_taken": [
                a if isinstance(a, dict) else {
                    "action": getattr(a, "action", ""),
                    "target": getattr(a, "target", ""),
                    "success": getattr(a, "success", False),
                    "verified": getattr(a, "verified", False),
                }
                for a in getattr(result, "actions_taken", [])
            ],
            "verified": bool(getattr(getattr(result, "verification", None),
                                     "verified", False)),
            "remaining_work": list(getattr(result, "remaining_work", [])),
            "errors": list(getattr(result, "errors", [])),
        })
        self.observations.extend(list(getattr(result, "observations", [])))
        self.current_task = None

    def reset(self) -> None:
        self.current_task = None
        self.observations.clear()
        self.execution_history.clear()


__all__ = ["DesktopLocalState"]
