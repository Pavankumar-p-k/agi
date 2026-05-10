from __future__ import annotations

from typing import Any

from ..contracts import Reflection


class ReflectionEngine:
    def __init__(self, memory: Any) -> None:
        self.memory = memory

    def reflect(self, plan: Any, execution: Any) -> Reflection:
        if execution.success:
            lessons = ["Successful tool chain should be preferred for similar prompts."]
            follow_up = ["Persist workflow in long-term memory."]
            status = "success"
        else:
            failed_tool = execution.results[-1].tool if execution.results else "unknown"
            lessons = [f"Strengthen validation around `{failed_tool}` arguments and runtime permissions."]
            follow_up = [f"Review tool `{failed_tool}` and add targeted retries or safer defaults."]
            status = "needs_improvement"
        reflection = Reflection(status=status, lessons=lessons, follow_up_actions=follow_up)
        self.memory.remember("reflection", " | ".join(lessons), {"plan_id": plan.plan_id, "status": status})
        return reflection

