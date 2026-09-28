"""SubAgentAdapter — base for adapter bridges (SubAgent -> execute() contract)."""
from __future__ import annotations

import re
from typing import Any, Optional

ADAPTER_TIMEOUT = 300


class SubAgentAdapter:
    """Bridges a SubAgent (run/mode API) into the BaseAgent contract
    (agent_id / priority / can_handle / execute -> AgentResult)."""

    agent_id = "base"
    priority = 50
    keywords: list[str] = []

    def __init__(self, **kwargs: Any):
        self._kwargs = kwargs

    def can_handle(self, goal: str) -> bool:
        """Word-boundary keyword match."""
        text = (goal or "").lower()
        return any(
            re.search(r"\b" + re.escape(kw.strip().lower()) + r"\b", text) is not None
            for kw in self.keywords if kw.strip()
        )

    async def execute(self, goal: str, context: Optional[Any] = None, **kwargs: Any) -> Any:
        from core.agents.base import AgentResult
        try:
            result = await self._run_agent(goal, **kwargs)
            return AgentResult(
                success=bool(getattr(result, "success", False)),
                output=str(getattr(result, "output", "")),
                agent_id=self.agent_id,
                error=str(getattr(result, "error", "")),
                duration=float(getattr(result, "duration_s", 0.0)),
                metadata={"mode": getattr(result, "mode", "")},
            )
        except Exception as exc:  # noqa: BLE001 — never raise out of execute()
            return AgentResult(success=False, output="", agent_id=self.agent_id,
                               error=f"{type(exc).__name__}: {exc}")

    async def _run_agent(self, goal: str, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError
