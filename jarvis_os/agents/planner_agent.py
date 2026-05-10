from __future__ import annotations

from ._base import BaseAgent
from ..contracts import AgentProfile


class PlannerAgent(BaseAgent):
    def __init__(self, planner) -> None:
        super().__init__(
            AgentProfile(name="planner_agent", focus="task decomposition", strengths=["planning", "sequencing", "orchestration"]),
            planner,
        )

