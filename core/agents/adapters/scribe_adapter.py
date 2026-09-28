"""ScribeAdapter — documentation specialist."""
from __future__ import annotations

from typing import Any, Optional

from core.agents._sub_agent_base import AgentResult, SubAgent
from core.agents.base import AgentResult as _ToolResult


class ScribeAgent(SubAgent):
    """Writes documentation, READMEs, API references, changelogs."""

    NAME = "SCRIBE"
    DEFAULT_MODE = "docs"
    MODES = {
        "docs": "You are SCRIBE, a technical writer. Produce clean markdown documentation with examples.",
        "readme": "You are SCRIBE writing a README: what it does, install, quickstart, API summary.",
        "reference": "You are SCRIBE writing an API reference: signatures, params, returns, examples.",
        "changelog": "You are SCRIBE writing a changelog entry in Keep-a-Changelog format.",
    }


class ScribeAdapter:
    agent_id = "scribe"
    priority = 50
    keywords = ["documentation", "document the", "write docs", "readme",
                "api reference", "changelog"]

    def __init__(self, **kwargs: Any):
        self._agent = ScribeAgent(**kwargs)

    @property
    def agent(self) -> ScribeAgent:
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
