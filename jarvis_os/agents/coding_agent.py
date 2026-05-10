from __future__ import annotations

from ._base import BaseAgent
from ..contracts import AgentProfile


class CodingAgent(BaseAgent):
    def __init__(self, planner) -> None:
        super().__init__(
            AgentProfile(name="coding_agent", focus="code analysis and generation", strengths=["analysis", "debugging", "python"]),
            planner,
        )

