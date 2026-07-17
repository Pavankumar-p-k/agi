"""BaseAgent — unified interface for all specialized agents.

Each agent owns a capability domain: research, build, test, browse, memory, email.
The agent lifecycle is:

  initialize(config: dict) -> bool
    ↓ True
  plan(context: dict) -> list[StepDefinition] | None
    ↓ plan exists
  execute(context: ExecutionContext) -> dict
    ↓ finished
  verify(context: ExecutionContext, result: dict) -> bool
    ↓ True/False
  report(context: ExecutionContext, result: dict) -> dict
    ↓ reports metrics/metadata
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from core.execution import ExecutionManager
from core.workflow.context import ExecutionContext
from core.workflow.models import StepDefinition

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for all specialized agents in the multi-agent graph.

    Subclasses must set agent_id and capabilities at minimum.
    Every agent now executes through ``ExecutionManager`` for lifecycle
    events, memory recording, and workflow integration.
    """

    agent_id: str = ""
    capabilities: list[str] = []
    priority: int = 100

    def __init__(self, execution_manager: ExecutionManager | None = None, **kwargs: Any):
        self._execution_manager = execution_manager or ExecutionManager()
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

    async def execute_with_lifecycle(
        self, context: ExecutionContext | None = None,
    ) -> dict:
        """Execute with ``ExecutionManager`` lifecycle tracking.

        Publishes started/progress/completed/failed events and records
        memory traces automatically.  Subclasses should call this instead
        of ``execute()`` for canonical lifecycle integration.
        """
        ec = context or ExecutionContext(
            workflow_id=f"agent_{self.agent_id}",
            owner=self.agent_id,
            session_id="",
        )
        exec_ctx = self._execution_manager.create_context(
            source=f"agent:{self.agent_id}",
            metadata={"agent_id": self.agent_id},
        )

        self._execution_manager.publish_progress(
            exec_ctx, f"agent_start:{self.agent_id}",
        )
        try:
            result = await self.execute(context)
            if result.get("exit_code", -1) == 0:
                self._execution_manager.publish_completed(exec_ctx, result)
            else:
                self._execution_manager.publish_failed(
                    exec_ctx, result.get("error", "non-zero exit"),
                )
            self._execution_manager.record_trace(
                exec_ctx, f"agent:{self.agent_id}",
                result.get("output", ""),
                result.get("exit_code", -1) == 0,
                action_params={"agent_id": self.agent_id},
            )
            return result
        except Exception as exc:
            self._execution_manager.publish_failed(exec_ctx, str(exc))
            self._execution_manager.record_trace(
                exec_ctx, f"agent:{self.agent_id}", str(exc), False,
            )
            return {"output": "", "exit_code": 1, "error": str(exc)}

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
