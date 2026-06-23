"""BaseAgent — abstract interface for all specialized agents.

Each agent owns a capability domain: research, build, test, browse, memory, email.
The agent lifecycle is:

  can_handle(goal: str) -> bool
    ↓ True
  plan(context: dict) -> list[StepDefinition] | None
    ↓ plan exists
  execute(context: ExecutionContext) -> dict
    ↓ finished
  verify(context: ExecutionContext, result: dict) -> bool
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from core.workflow.context import ExecutionContext
from core.workflow.models import StepDefinition

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for all specialized agents in the multi-agent graph.

    Subclasses must set agent_id and capabilities at minimum.
    """

    agent_id: str = ""
    capabilities: list[str] = []
    priority: int = 100

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    # ── Detection ──────────────────────────────────────────────────────────
    def can_handle(self, goal: str) -> bool:
        """Return True if this agent can handle the given goal.

        Uses keyword matching against self.capabilities by default.
        Subclasses may override for more sophisticated detection.
        """
        goal_lower = goal.lower()
        return any(kw in goal_lower for kw in self.capabilities)

    # ── Planning ───────────────────────────────────────────────────────────
    def plan(self, context: dict) -> list[StepDefinition] | None:
        """Generate a list of workflow steps to accomplish the goal.

        Returns None if planning is not possible (agent should be skipped).
        Default implementation returns a single-step plan executing the agent.
        Subclasses may generate multi-step plans.
        """
        return None

    # ── Execution ──────────────────────────────────────────────────────────
    @abstractmethod
    async def execute(self, context: ExecutionContext | None = None) -> dict:
        """Execute the agent's task within the given context.

        Must return a dict with at minimum:
          {"output": str, "exit_code": int}

        May also include:
          {"_artifacts": dict, "error": str}
        """
        ...

    # ── Verification ───────────────────────────────────────────────────────
    def verify(self, context: ExecutionContext | None = None,
               result: dict | None = None) -> bool:
        """Check that the agent's execution produced valid output.

        Default: return True if exit_code == 0 and output is non-empty.
        """
        if not result:
            return False
        if result.get("exit_code", -1) != 0:
            return False
        if not result.get("output"):
            return False
        return True
