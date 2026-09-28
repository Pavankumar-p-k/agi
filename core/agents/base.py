"""Agent base classes: AgentResult + BaseAgent (tool agents)."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AgentResult:
    """Uniform result for every agent execution."""
    success: bool = False
    output: str = ""
    agent_id: str = ""
    error: str = ""
    duration: float = 0.0
    exit_code: int = 0
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration": self.duration,
            "exit_code": self.exit_code,
            "artifacts": dict(self.artifacts),
            "metadata": dict(self.metadata),
        }


class BaseAgent:
    """Base class for all tool agents (build/email/memory/research/test/browser).

    Subclasses set `agent_id`, `keywords` and `priority`, and implement
    `_execute_impl`. The public `execute()` wraps timing + error handling so
    failures always produce an AgentResult instead of raising.
    """

    agent_id: str = "base"
    keywords: list[str] = []
    priority: int = 10
    description: str = ""

    def __init__(self, **kwargs: Any):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def can_handle(self, goal: str) -> bool:
        """Word-boundary keyword match (so 'tab' doesn't hit 'database')."""
        text = (goal or "").lower()
        return any(
            re.search(r"\b" + re.escape(kw.strip().lower()) + r"\b", text) is not None
            for kw in self.keywords if kw.strip()
        )

    async def execute(self, goal: Any, context: Optional[Any] = None, **kwargs: Any) -> AgentResult:
        # Polymorphic entry: accept a plain goal string or an ExecutionContext
        # as the first argument (agent-driven executor passes the context).
        if not isinstance(goal, str):
            context = goal
            goal = str(getattr(goal, "goal", "") or "")
        start = time.monotonic()
        try:
            result = await self._execute_impl(goal, context, **kwargs)
            if isinstance(result, AgentResult):
                result.agent_id = self.agent_id
                result.duration = time.monotonic() - start
                return result
            # Plain string output from _execute_impl
            return AgentResult(
                success=True,
                output=str(result),
                agent_id=self.agent_id,
                duration=time.monotonic() - start,
            )
        except Exception as exc:  # noqa: BLE001 — never raise out of execute()
            return AgentResult(
                success=False,
                output="",
                agent_id=self.agent_id,
                error=f"{type(exc).__name__}: {exc}",
                duration=time.monotonic() - start,
            )

    async def _execute_impl(self, goal: str, context: Optional[Any] = None, **kwargs: Any) -> Any:
        raise NotImplementedError
