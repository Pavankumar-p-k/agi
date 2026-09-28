"""AtlasAdapter — data/SQL specialist."""
from __future__ import annotations

from typing import Any, Optional

from core.agents._sub_agent_base import AgentResult, SubAgent
from core.agents.base import AgentResult as _ToolResult


class AtlasAgent(SubAgent):
    """SQL generation, schema design, data analysis."""

    NAME = "ATLAS"
    DEFAULT_MODE = "query"
    MODES = {
        "query": "You are ATLAS, a data engineer. Output ONLY the SQL query that answers the request, then a one-line explanation.",
        "schema": "You are ATLAS designing a schema. Output CREATE TABLE statements with keys and indexes.",
        "analyze": "You are ATLAS analyzing data. Describe structure, quality issues, and notable patterns.",
    }


class AtlasAdapter:
    agent_id = "atlas"
    priority = 50
    keywords = ["sql query", "database query", "select from", "schema",
                "migrate database", "query the database"]

    def __init__(self, **kwargs: Any):
        self._agent = AtlasAgent(**kwargs)

    @property
    def agent(self) -> AtlasAgent:
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
