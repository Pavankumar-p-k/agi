from __future__ import annotations

from ._base import BaseAgent
from ..contracts import AgentProfile


class ResearchAgent(BaseAgent):
    def __init__(self, planner) -> None:
        super().__init__(
            AgentProfile(name="research_agent", focus="web research and synthesis", strengths=["search", "news", "summaries"]),
            planner,
        )

