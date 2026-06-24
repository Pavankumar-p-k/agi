"""Multi-page browser research tool.

Orchestrates:
  Question → ResearchPlanner → Browser Searches → Fact Extraction
    → Research Pipeline (retrieve, reason, synthesize) → Report

Bridges browser-based fact extraction (BrowserFactExtractor) with the
research pipeline (FactStore, FactReasoner, FactSynthesizer).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from core.fact_extraction.bridge import bridge_batch
from core.fact_extraction.extractor import BrowserFactExtractor
from core.fact_extraction.store import BrowserFactStore

logger = logging.getLogger(__name__)

_MAX_PAGES = 5
_MAX_ITERATIONS = 2


_browser_extractor = BrowserFactExtractor()
_browser_fact_store = BrowserFactStore()


async def do_browser_research(
    question: str,
    session_id: str | None = None,
    max_pages: int = _MAX_PAGES,
    max_iterations: int = _MAX_ITERATIONS,
) -> dict[str, Any]:
    """Run multi-page research using the browser.

    Steps:
      1. Decompose question into sub-goals via ResearchPlanner
      2. For each goal, search the web via browser and visit result pages
      3. Extract facts from each page using BrowserFactExtractor
      4. Bridge to research pipeline Fact objects and store in FactStore
      5. Analyze contradictions/agreements via FactReasoner
      6. Synthesize a structured research report via FactSynthesizer
      7. Check for gaps and iterate if needed
      8. Return the final report + metadata
    """
    all_facts: list[dict] = []
    visited_urls: set[str] = set()
    iteration = 0
    sources: list[str] = []

    # Phase 1: Plan the research
    plan = _create_plan(question)
    queries = _get_queries(plan)

    # Phase 2-4: Browser research loop
    while iteration < max_iterations and len(visited_urls) < max_pages:
        if not queries:
            break
        query = queries.pop(0)
        page_facts, page_urls = await _research_query(
            query, session_id, visited_urls, max_pages,
        )
        all_facts.extend(page_facts)
        sources.extend(page_urls)
        iteration += 1

        # Check if we need more queries from GapDetector
        if not queries and iteration < max_iterations:
            queries = _get_follow_up_queries(plan, all_facts)

    # Phase 5-7: Analyze and synthesize
    report = _synthesize_report(question, all_facts, sources)
    return report


async def _research_query(
    query: str,
    session_id: str | None,
    visited_urls: set[str],
    max_pages: int,
) -> tuple[list[dict], list[str]]:
    """Execute a single search query via browser and extract facts."""
    from core.tools.browser_tools import (
        do_browser_fill,
        do_browser_navigate,
        do_browser_press,
        do_browser_snapshot,
    )

    all_facts: list[dict] = []
    page_urls: list[str] = []

    # Step 1: Navigate to search engine
    search_url = _pick_search_engine(query)
    result = await do_browser_navigate(search_url, session_id=session_id)
    if not result or result.get("error"):
        logger.warning("Research: navigate failed for %s: %s", search_url, result)
        return all_facts, page_urls

    await asyncio.sleep(0.5)

    # Step 2: Fill and submit search
    for sel in ("input[name=q]", "input[type=search]", "textarea"):
        fill = await do_browser_fill(sel, query, session_id=session_id, force=True)
        if fill and not fill.get("error"):
            await do_browser_press(sel, "Enter", session_id=session_id)
            await asyncio.sleep(1.5)
            break

    # Step 3: Take snapshot and extract search results
    snap = await do_browser_snapshot(session_id=session_id)
    if not snap or snap.get("error"):
        logger.warning("Research: snapshot failed after search")
        return all_facts, page_urls

    # Step 4: Extract links from results and visit pages
    links = _extract_result_links(snap)
    for link in links[:3]:
        if len(visited_urls) >= max_pages:
            break
        href = link.get("href", "").strip()
        if not href or href in visited_urls:
            continue
        visited_urls.add(href)
        page_urls.append(href)
        page_facts = await _visit_and_extract(href, session_id)
        all_facts.extend(page_facts)

    return all_facts, page_urls


async def _visit_and_extract(
    url: str,
    session_id: str | None,
) -> list[dict]:
    """Navigate to a URL, snapshot, and extract facts."""
    from core.tools.browser_tools import do_browser_navigate, do_browser_snapshot

    facts: list[dict] = []

    result = await do_browser_navigate(url, session_id=session_id)
    if not result or result.get("error"):
        logger.warning("Research: navigate failed to %s", url)
        return facts

    await asyncio.sleep(1.0)

    snap = await do_browser_snapshot(session_id=session_id)
    if not snap or snap.get("error"):
        return facts

    inner = snap.get("result", snap)
    if not isinstance(inner, dict):
        return facts

    # Extract facts using BrowserFactExtractor
    extracted = _browser_extractor.extract_from_snapshot(inner, url, max_facts=15)
    if not extracted:
        return facts

    # Bridge to research pipeline and store
    research_facts = bridge_batch(extracted)
    try:
        from core.research.storage import FactStore
        store = FactStore()
        for rf in research_facts:
            store.insert_fact(rf)
    except Exception:
        pass

    # Also store in browser fact store
    try:
        _browser_fact_store.store_facts(extracted)
    except Exception:
        pass

    # Return serializable fact dicts
    serialized = _browser_extractor.to_json_serializable(extracted)
    facts.extend(serialized)
    return facts


def _synthesize_report(
    question: str,
    all_facts: list[dict],
    sources: list[str],
) -> dict[str, Any]:
    """Convert extracted facts to a structured research report."""
    if not all_facts:
        return {
            "question": question,
            "sources_consulted": sources,
            "total_facts": 0,
            "summary": "No facts could be extracted from the pages visited.",
            "facts": [],
            "agreements": [],
            "contradictions": [],
            "gaps": ["No information found for this topic."],
            "overall_confidence": 0.0,
            "recommendations": ["Try a different search query or visit more pages."],
        }

    # Bridge to research pipeline Fact objects for analysis
    from core.research.models import Fact as ResearchFact
    research_facts: list[ResearchFact] = []
    for fd in all_facts:
        rf = ResearchFact(
            fact_id=fd.get("fact_id", ""),
            source_url=fd.get("source_url", ""),
            claim=fd.get("claim", ""),
            confidence=fd.get("confidence", 0.5),
            category=fd.get("category", "general"),
            tags=fd.get("tags", []),
            timestamp=datetime.utcnow(),
            metadata={"entity": fd.get("entity")},
        )
        research_facts.append(rf)

    # Analyze via research pipeline
    agreements: list[str] = []
    contradictions: list[str] = []
    gaps: list[str] = []
    overall_confidence = 0.0

    try:
        from core.research.reasoner import FactReasoner
        from core.research.synthesizer import FactSynthesizer

        reasoner = FactReasoner()
        comparison = reasoner.analyze(research_facts)

        if comparison:
            agreements = [a.summary() for a in comparison.agreements]
            contradictions = [c.summary() for c in comparison.contradictions]
            gaps = [g.question for g in comparison.gaps]

        synthesizer = FactSynthesizer()
        report = synthesizer.synthesize(question, research_facts, comparison)
        if report:
            overall_confidence = report.overall_confidence
            return {
                "question": question,
                "sources_consulted": list(set(sources)),
                "total_facts": len(all_facts),
                "summary": report.summary,
                "facts": all_facts,
                "agreements": report.agreements,
                "contradictions": report.conflicts,
                "gaps": report.gaps,
                "overall_confidence": report.overall_confidence,
                "recommendations": report.recommendations,
            }
    except ImportError:
        logger.debug("Research pipeline not fully available, returning raw facts")
    except Exception as e:
        logger.warning("Research synthesis error: %s", e)

    # Fallback: return raw facts
    return {
        "question": question,
        "sources_consulted": list(set(sources)),
        "total_facts": len(all_facts),
        "summary": f"Extracted {len(all_facts)} facts from {len(set(sources))} sources.",
        "facts": all_facts,
        "agreements": agreements,
        "contradictions": contradictions,
        "gaps": gaps,
        "overall_confidence": overall_confidence,
        "recommendations": ["Review individual facts for detailed information."],
    }


# ── Helpers ──────────────────────────────────────────────────────


def _create_plan(question: str) -> Any:
    """Decompose question into a research plan."""
    try:
        from core.research.planner import ResearchPlanner
        planner = ResearchPlanner()
        return planner.plan(question, max_iterations=_MAX_ITERATIONS)
    except ImportError:
        return None
    except Exception as e:
        logger.warning("Research planner error: %s", e)
        return None


def _get_queries(plan: Any) -> list[str]:
    """Extract search queries from a research plan."""
    if plan is None:
        return [plan] if isinstance(plan, str) else []

    queries: list[str] = []
    try:
        for goal in getattr(plan, "goals", []):
            for sq in getattr(goal, "search_queries", []):
                q = sq.query if hasattr(sq, "query") else (sq.get("query") if isinstance(sq, dict) else str(sq))
                if q:
                    queries.append(q)
    except Exception:
        pass

    if not queries:
        queries = [plan.question if hasattr(plan, "question") else str(plan)]

    return queries


def _get_follow_up_queries(plan: Any, all_facts: list[dict]) -> list[str]:
    """Use GapDetector to find follow-up queries."""
    try:
        from core.research.gap_detector import GapDetector
        from core.research.models import Fact as ResearchFact

        research_facts: list[ResearchFact] = []
        for fd in all_facts:
            rf = ResearchFact(
                fact_id=fd.get("fact_id", ""),
                source_url=fd.get("source_url", ""),
                claim=fd.get("claim", ""),
                confidence=fd.get("confidence", 0.5),
                category=fd.get("category", "general"),
            )
            research_facts.append(rf)

        detector = GapDetector()
        gap = detector.analyze(plan, research_facts)
        if gap and hasattr(gap, "follow_up_queries"):
            return gap.follow_up_queries
    except Exception:
        pass
    return []


def _pick_search_engine(query: str) -> str:
    return "https://www.google.com"


def _extract_result_links(snap: dict) -> list[dict]:
    """Extract result links from a search engine snapshot."""
    inner = snap.get("result", snap)
    if not isinstance(inner, dict):
        return []
    links = inner.get("links", [])
    if not isinstance(links, list):
        return []
    return [l for l in links if isinstance(l, dict) and l.get("href")]
