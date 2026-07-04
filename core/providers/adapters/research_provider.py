from __future__ import annotations

import logging
import time
from typing import Any

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class ResearchProvider(ExecutionProvider):
    provider_id = "research"
    name = "Research Pipeline"
    version = "1.0.0"
    priority = 10
    installed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=[
                "research",
                "find",
                "learn",
                "investigate",
                "explore",
                "analysis",
            ],
            features=[
                "fact_extraction",
                "question_answering",
                "source_synthesis",
                "gap_analysis",
                "report_generation",
            ],
        )

    async def health(self) -> ProviderHealth:
        try:
            from core.research.storage import FactStore
            store = FactStore()
            count = store.count_facts()
            logger.debug("[ResearchProvider] Health OK (%d facts)", count)
            return ProviderHealth(
                status=ProviderHealthStatus.HEALTHY,
                latency_ms=0.0,
                last_checked=time.time(),
            )
        except Exception as e:
            logger.debug("[ResearchProvider] Health check failed: %s", e)
            return ProviderHealth(
                status=ProviderHealthStatus.DOWN,
                error=str(e),
                last_checked=time.time(),
            )

    async def execute(
        self, task: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ExecutionResult:
        question = task.get("goal", task.get("question", ""))
        mode = task.get("mode", "full")
        start = time.monotonic()

        try:
            if mode == "quick":
                return await self._quick_research(question, task, start)
            return await self._full_research(question, task, start)
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("[ResearchProvider] Execution failed: %s", e)
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                duration_ms=elapsed,
                metadata={"provider": "research", "mode": mode},
            )

    async def _quick_research(
        self, question: str, task: dict[str, Any], start: float
    ) -> ExecutionResult:
        from core.tools.browser_research import do_browser_research

        max_pages = task.get("max_pages", 3)
        session_id = task.get("session_id", "")

        result = await do_browser_research(
            question=question,
            session_id=session_id,
            max_pages=max_pages,
            max_iterations=1,
        )
        elapsed = (time.monotonic() - start) * 1000
        success = result.get("status") != "error"

        return ExecutionResult(
            success=success,
            output=str(result.get("report", result.get("summary", str(result)))),
            exit_code=0 if success else 1,
            duration_ms=elapsed,
            artifacts={},
            metadata={
                "provider": "research",
                "mode": "quick",
                "facts_found": result.get("facts_count", 0),
                "sources_visited": result.get("pages_visited", 0),
            },
        )

    async def _full_research(
        self, question: str, task: dict[str, Any], start: float
    ) -> ExecutionResult:
        from core.research.planner import ResearchPlanner
        from core.research.storage import FactStore

        planner = ResearchPlanner()
        plan = planner.plan(question, max_iterations=task.get("max_iterations", 5))

        queries = planner.generate_queries(plan)
        facts_collected: list[dict] = []
        store = FactStore()

        for query in queries:
            try:
                from core.tools.browser_research import do_browser_research
                result = await do_browser_research(
                    question=query.query,
                    session_id=task.get("session_id", ""),
                    max_pages=2,
                    max_iterations=1,
                )
                facts = result.get("facts", [])
                for f in facts:
                    facts_collected.append(f)
                    if hasattr(store, "insert_fact"):
                        try:
                            store.insert_fact(f)
                        except Exception:
                            pass
                query.executed = True
                query.facts_found = len(facts)
            except Exception as e:
                logger.debug("[ResearchProvider] Query failed: %s - %s", query.query, e)

        plan.total_facts_collected = len(facts_collected)
        plan = planner.refine(plan, facts_collected)

        from core.research.synthesizer import FactSynthesizer
        synthesizer = FactSynthesizer()
        report = synthesizer.synthesize(question, facts_collected)

        elapsed = (time.monotonic() - start) * 1000
        success = plan.status.name != "STOPPED" or len(facts_collected) > 0

        return ExecutionResult(
            success=success,
            output=str(report.to_dict() if hasattr(report, "to_dict") else report),
            exit_code=0 if success else 1,
            duration_ms=elapsed,
            artifacts={},
            metadata={
                "provider": "research",
                "mode": "full",
                "facts_collected": len(facts_collected),
                "goals_planned": len(plan.goals),
                "goals_answered": len(plan.answered_goals()),
                "iterations": plan.iteration,
                "completion_ratio": plan.completion_ratio(),
            },
        )

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 1000.0
