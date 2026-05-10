from __future__ import annotations

from typing import Any

from ..contracts import AgentProfile


class BaseAgent:
    def __init__(self, profile: AgentProfile, planner: Any) -> None:
        self.profile = profile
        self.planner = planner

    def plan(self, prompt: str, intent: Any, analysis: dict[str, Any]) -> Any:
        return self.planner.build_plan(prompt, intent, analysis)

