"""Bounded browser research planning and report helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResearchPlan:
    question: str
    goals: list[Any] = field(default_factory=list)


def _pick_search_engine(_question: str) -> str:
    return "https://www.google.com"


def _create_plan(question: str) -> ResearchPlan:
    return ResearchPlan(question=str(question or ""))


def _extract_result_links(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return []
    links = snapshot.get("links")
    if links is None and isinstance(snapshot.get("result"), dict):
        links = snapshot["result"].get("links")
    return [link for link in (links or []) if isinstance(link, dict) and link.get("href")]


def _get_queries(plan: Any) -> list[str]:
    if plan is None:
        return []
    queries: list[str] = []
    for goal in getattr(plan, "goals", []) or []:
        for query in getattr(goal, "search_queries", []) or []:
            value = query.get("query") if isinstance(query, dict) else getattr(query, "query", None)
            if value:
                queries.append(str(value))
    if queries:
        return queries
    question = getattr(plan, "question", None)
    return [str(question)] if question else []


def _get_follow_up_queries(plan: Any, facts: list[dict[str, Any]]) -> list[str]:
    if plan is None or not facts:
        return []
    return []


def _synthesize_report(question: str, facts: list[dict[str, Any]], sources: list[str]) -> dict[str, Any]:
    unique_sources = list(dict.fromkeys(str(source) for source in sources if source))
    summary = f"No facts found for {question}" if not facts else f"Collected {len(facts)} fact(s) for {question}"
    return {
        "question": question,
        "total_facts": len(facts),
        "facts": facts,
        "sources_consulted": unique_sources,
        "summary": summary,
        "recommendations": ["Broaden the query or consult additional sources."] if not facts else [],
    }


async def do_browser_research(question: str, max_pages: int = 3, **_kwargs: Any) -> dict[str, Any]:
    # Browser execution is intentionally not inferred here.  Without a
    # verified browser backend, return a truthful empty report.
    return _synthesize_report(question, [], [])


async_do_browser_research = do_browser_research
