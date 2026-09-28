"""NexusAdapter — comparison/evaluation specialist."""
from __future__ import annotations

from typing import Any, Optional

from core.agents._sub_agent_base import AgentResult, SubAgent
from core.agents.base import AgentResult as _ToolResult


class NexusAgent(SubAgent):
    """Compares options, frameworks, approaches."""

    NAME = "NEXUS"
    DEFAULT_MODE = "compare"
    MODES = {
        "compare": "You are NEXUS, an expert at structured comparisons. Use a comparison table followed by a clear recommendation.",
        "research": "You are NEXUS in research mode. Gather and organize facts about the topic from your knowledge.",
        "brief": "You are NEXUS. Answer with a tight executive brief: 3 bullets max.",
    }


class NexusAdapter:
    agent_id = "nexus"
    priority = 50
    keywords = ["compare", "versus", " vs ", "difference between", "evaluate options",
                "trade-offs", "tradeoffs"]

    def __init__(self, **kwargs: Any):
        self._agent = NexusAgent(**kwargs)

    @property
    def agent(self) -> NexusAgent:
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
