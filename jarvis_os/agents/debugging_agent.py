from __future__ import annotations

from ._base import BaseAgent
from ..contracts import AgentProfile


class DebuggingAgent(BaseAgent):
    def __init__(self, planner) -> None:
        super().__init__(
            AgentProfile(name="debugging_agent", focus="failure analysis", strengths=["triage", "root cause analysis", "retries"]),
            planner,
        )

