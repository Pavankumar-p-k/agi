"""OracleAdapter — planning/architecture specialist."""
from __future__ import annotations

from typing import Any, Optional

from core.agents._sub_agent_base import AgentResult, SubAgent
from core.agents.base import AgentResult as _ToolResult


class OracleAgent(SubAgent):
    """Plans architecture, roadmaps, milestones."""

    NAME = "ORACLE"
    DEFAULT_MODE = "plan"
    MODES = {
        "plan": "You are ORACLE, a principal architect. Produce a numbered step-by-step plan with clear deliverables per step.",
        "architecture": "You are ORACLE designing system architecture. Specify components, data flow, and trade-offs.",
        "roadmap": "You are ORACLE building a roadmap. Organize into phases with milestones and estimates.",
    }


class OracleAdapter:
    agent_id = "oracle"
    priority = 50
    keywords = ["plan", "architecture", "design strategy", "roadmap",
                "break down", "milestones"]

    def __init__(self, **kwargs: Any):
        self._agent = OracleAgent(**kwargs)

    @property
    def agent(self) -> OracleAgent:
        return self._agent

    def can_handle(self, goal: str) -> bool:
        text = (goal or "").lower()
        return any(kw.lower() in text for kw in self.keywords)

    def info(self) -> dict[str, Any]:
        return {**self._agent.info(), "agent_id": self.agent_id, "priority": self.priority}

    async def run(self, task: str, mode: str = "", **kwargs: Any) -> Any:
        return await self._agent.run(task, mode=mode, **kwargs)

    async def execute(self, goal: str, context: Optional[Any] = None, **kwargs: Any) -> _ToolResult:
        result = await self._agent.run(goal, **kwargs)
        return _ToolResult(success=result.success, output=result.output,
                           agent_id=self.agent_id, error=result.error,
                           duration=result.duration_s, metadata={"mode": result.mode})
