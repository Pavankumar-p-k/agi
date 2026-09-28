"""CipherAdapter — security audit specialist."""
from __future__ import annotations

from typing import Any, Optional

from core.agents._sub_agent_base import AgentResult, SubAgent
from core.agents.base import AgentResult as _ToolResult


class CipherAgent(SubAgent):
    """Security audits, vulnerability analysis, hardening advice."""

    NAME = "CIPHER"
    DEFAULT_MODE = "audit"
    MODES = {
        "audit": "You are CIPHER, a security auditor. List findings ordered by severity (CRITICAL/HIGH/MEDIUM/LOW) with fixes.",
        "threats": "You are CIPHER threat-modeling. Use STRIDE to enumerate threats and mitigations.",
        "harden": "You are CIPHER hardening a system. Give concrete, prioritized hardening steps.",
    }


class CipherAdapter:
    agent_id = "cipher"
    priority = 50
    keywords = ["security", "audit code", "vulnerability", "cve", "encrypt",
                "threat model", "harden"]

    def __init__(self, **kwargs: Any):
        self._agent = CipherAgent(**kwargs)

    @property
    def agent(self) -> CipherAgent:
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
