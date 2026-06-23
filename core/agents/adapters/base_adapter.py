"""SubAgentAdapter — wraps a SubAgent (LLM) as a BaseAgent (graph-routable).

Every adapter inherits:
  - asyncio.wait_for timeout (env JARVIS_ADAPTER_TIMEOUT, default 60s)
  - Agent metadata (agent, agent_type, mode) on every result
  - Error handling for TimeoutError and generic exceptions
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from core.agents.base import BaseAgent
from core.sub_agents.base_agent import SubAgent

logger = logging.getLogger(__name__)

_ADAPTER_TIMEOUT = int(os.getenv("JARVIS_ADAPTER_TIMEOUT", "60"))


class SubAgentAdapter(BaseAgent):
    """Bridge: SubAgent (LLM specialist) -> BaseAgent (graph-routable).

    Subclasses must set:
      sub_agent_class: type[SubAgent]  — the SubAgent to wrap
      default_mode: str                — default execution mode
    """

    sub_agent_class: type[SubAgent] | None = None
    default_mode: str = "default"
    priority: int = 50

    async def execute(self, context: Any = None) -> dict:
        task = ""
        if context and hasattr(context, "variables"):
            task = context.variables.get("goal", "")
        mode = ""
        if context and hasattr(context, "variables"):
            mode = context.variables.get("mode", self.default_mode)

        if not self.sub_agent_class:
            return {
                "output": "",
                "exit_code": 1,
                "error": "no sub_agent_class configured",
                "agent": self.agent_id,
                "agent_type": "llm_specialist",
                "mode": mode,
            }

        agent = self.sub_agent_class()
        try:
            result = await asyncio.wait_for(
                agent.run(task, mode),
                timeout=_ADAPTER_TIMEOUT,
            )
            return {
                "output": result.output,
                "exit_code": 0 if result.success else 1,
                "_artifacts": {},
                "agent": self.agent_id,
                "agent_type": "llm_specialist",
                "mode": mode,
                "result": result.to_dict() if result else {},
            }
        except asyncio.TimeoutError:
            logger.warning(
                "SubAgentAdapter: %s timed out after %ds (mode=%s)",
                self.agent_id, _ADAPTER_TIMEOUT, mode,
            )
            return {
                "output": "",
                "exit_code": 1,
                "error": "adapter_timeout",
                "agent": self.agent_id,
                "agent_type": "llm_specialist",
                "mode": mode,
            }
        except Exception as e:
            logger.exception("SubAgentAdapter: %s failed (mode=%s): %s", self.agent_id, mode, e)
            return {
                "output": "",
                "exit_code": 1,
                "error": str(e),
                "agent": self.agent_id,
                "agent_type": "llm_specialist",
                "mode": mode,
            }
