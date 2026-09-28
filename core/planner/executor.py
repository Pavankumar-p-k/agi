"""PlannerExecutor — executes plans via an injected execute_fn."""
from __future__ import annotations

from typing import Any, Awaitable, Callable


class PlannerExecutor:
    """Thin shell the state machine drives; the execute_fn does the work."""

    def __init__(self, execute_fn: Callable[[str, Any], Awaitable[dict]] | None = None, **kwargs):
        self.execute_fn = execute_fn
        for k, v in kwargs.items():
            setattr(self, k, v)

    async def execute(self, goal: str, **kwargs) -> dict[str, Any]:
        if self.execute_fn is None:
            from core.agents.executor import make_agent_execute_fn
            self.execute_fn = make_agent_execute_fn()
        return await self.execute_fn(goal, self)
