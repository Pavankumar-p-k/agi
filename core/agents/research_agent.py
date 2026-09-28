"""ResearchAgent — handles research sub-goals via search + synthesis."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.agents.base import AgentResult, BaseAgent


@dataclass
class ResearchSnapshot:
    queries_logged: int = 0
    last_query: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"queries_logged": self.queries_logged,
                "last_query": self.last_query, "timestamp": self.timestamp}


class ResearchAgent(BaseAgent):
    """Web research backed by tools.search_tool (SearXNG/DuckDuckGo)."""

    agent_id = "research"
    keywords = ["research", "investigate", "explore topic", "search for information"]
    priority = 10
    description = "Web research with source-backed summaries"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.queries_logged = 0
        self.last_query = ""

    def analyze(self) -> ResearchSnapshot:
        return ResearchSnapshot(
            queries_logged=self.queries_logged,
            last_query=self.last_query,
            timestamp=datetime.now().isoformat(),
        )

    async def _execute_impl(self, goal: str, context: Optional[Any] = None, **kwargs: Any) -> AgentResult:
        # LLM access goes through the Execution stage gateway (Rule 1).
        from core.pipeline.stages.execution import complete_async

        results: list[dict] = []
        try:
            from tools.search_fallback import search as _search
            results = _search(goal, max_results=5) or []
        except Exception:  # noqa: BLE001 — offline is acceptable
            results = []

        self.queries_logged += 1
        self.last_query = goal

        context_block = "\n".join(
            f"- {r.get('title', '')}: {r.get('snippet', '')[:200]}"
            for r in results[:5] if isinstance(r, dict)
        ) or "(no web results — answer from model knowledge)"

        result = await complete_async(
            f"Research question: {goal}\n\nWeb findings:\n{context_block}\n\n"
            "Summarize the key findings in 3-5 bullet points.",
            role="chat",
            system="You are a research assistant. Be factual and cite sources when given.",
        )
        if result.is_err():
            return AgentResult(success=False, output="", agent_id=self.agent_id,
                               error=str(result.unwrap()))
        return AgentResult(success=True, output=result.unwrap(), agent_id=self.agent_id)
