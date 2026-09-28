"""HeraldAdapter — communications/drafting specialist."""
from __future__ import annotations

from typing import Any, Optional

from core.agents._sub_agent_base import AgentResult, SubAgent
from core.agents.base import AgentResult as _ToolResult


class HeraldAgent(SubAgent):
    """Drafts newsletters, announcements, updates, messages."""

    NAME = "HERALD"
    DEFAULT_MODE = "draft"
    MODES = {
        "draft": "You are HERALD, a professional communicator. Draft clear, audience-appropriate copy.",
        "newsletter": "You are HERALD writing a newsletter: subject line, intro, sections, call-to-action.",
        "announce": "You are HERALD writing an announcement. Lead with the news, keep it under 150 words.",
    }


class HeraldAdapter:
    agent_id = "herald"
    priority = 50
    keywords = ["draft", "newsletter", "announcement", "press release",
                "write update", "compose message"]

    def __init__(self, **kwargs: Any):
        self._agent = HeraldAgent(**kwargs)

    @property
    def agent(self) -> HeraldAgent:
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
