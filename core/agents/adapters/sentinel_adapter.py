"""SentinelAdapter — diagnostics/troubleshooting specialist."""
from __future__ import annotations

from typing import Any, Optional

from core.agents._sub_agent_base import AgentResult, SubAgent
from core.agents.base import AgentResult as _ToolResult


class SentinelAgent(SubAgent):
    """Diagnoses errors, root-causes failures, analyzes logs."""

    NAME = "SENTINEL"
    DEFAULT_MODE = "diagnose"
    MODES = {
        "diagnose": "You are SENTINEL, a diagnostics expert. Hypothesis -> evidence -> most likely root cause -> fix.",
        "logs": "You are SENTINEL analyzing logs. Identify the failing component, the first error, and the cascade.",
        "watch": "You are SENTINEL monitoring. Report current health signals and any anomalies.",
    }


class SentinelAdapter:
    agent_id = "sentinel"
    priority = 50
    keywords = ["diagnose", "debug error", "troubleshoot", "root cause",
                "log analysis", "why is it failing"]

    def __init__(self, **kwargs: Any):
        self._agent = SentinelAgent(**kwargs)

    @property
    def agent(self) -> SentinelAgent:
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
