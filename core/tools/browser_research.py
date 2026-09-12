"""Bounded browser research: search -> select sources -> open -> inspect ->
extract -> compare -> detect conflicts -> evidence-backed report.

Deterministic and LLM-free: fact extraction is keyword/sentence based so the
flow works without a model; tools/deep_research.py remains the LLM-grade
pipeline for heavier questions.  Research never launches a browser by itself —
it uses an already-running session and otherwise returns a truthful empty
report (this keeps unit tests fast and side-effect free).

Page-derived text is untrusted data: every fact claim is wrapped with the
untrusted-content markers from core/browser/page_security.py before it leaves
this module.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_MAX_PAGE_CHARS = 6000
_PAGE_TIMEOUT_S = 45.0
_SEARCH_TIMEOUT_S = 60.0
_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have how in into is it its of on or "
    "that the their there these this to was were what when where which who will with "
    "you your can could should would do does did not".split()
)


@dataclass
class ResearchPlan:
    question: str
    goals: list[Any] = field(default_factory=list)


def _pick_search_engine(_question: str) -> str:
    return "https://www.google.com"


def _create_plan(question: str) -> ResearchPlan:
    """Build a bounded research plan: one primary query (LLM sub-questions are
    deep_research.py's job)."""
    plan = ResearchPlan(question=str(question or ""))
    if plan.question:
        plan.goals.append({
            "goal": plan.question,
            "search_queries": [{"query": plan.question}],
        })
    return plan


def _extract_result_links(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return []
    links = snapshot.get("links")
    if links is None and isinstance(snapshot.get("result"), dict):
        inner = snapshot["result"]
        links = inner.get("links")
        if links is None and isinstance(inner.get("results"), list):
            # do_browser_search result shape: [{"title", "href"}, ...]
            links = inner.get("results")
    elif links is None and isinstance(snapshot.get("results"), list):
        links = snapshot.get("results")
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


def _keywords(question: str) -> list[str]:
    tokens = [t for t in re.findall(r"[a-zA-Z0-9]+", str(question or "").lower()) if t not in _STOPWORDS and len(t) > 2]
    return tokens or [t for t in re.findall(r"[a-zA-Z0-9]+", str(question or "").lower()) if t]


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if 40 <= len(p.strip()) <= 400]


def _extract_facts(text: str, url: str, keywords: list[str], max_facts: int = 8) -> list[dict[str, Any]]:
    """Keyword-scored sentence extraction (deterministic).  Claims are wrapped
    as untrusted page data."""
    from core.browser.page_security import UNTRUSTED_OPEN, UNTRUSTED_CLOSE

    lower_text = str(text or "").lower()
    facts: list[dict[str, Any]] = []
    scored: list[tuple[float, str]] = []
    for sentence in _sentences(text):
        lower_sentence = sentence.lower()
        score = sum(1 for kw in keywords if kw in lower_sentence)
        if score > 0:
            scored.append((float(score) + min(1.0, len(sentence) / 400.0), sentence))
    scored.sort(key=lambda item: item[0], reverse=True)
    for score, sentence in scored[:max_facts]:
        facts.append({
            "fact_id": uuid.uuid4().hex[:12],
            "source_url": url,
            "claim": f"{UNTRUSTED_OPEN}{sentence}{UNTRUSTED_CLOSE}",
            "confidence": round(min(0.9, 0.5 + score / 10.0), 3),
            "category": "web",
            "tags": keywords[:6],
            "entity": _entity_of(sentence, keywords),
            "source_type": "paragraph",
            "attributes": {},
        })
    return facts


def _entity_of(sentence: str, keywords: list[str]) -> str:
    """Cheap entity key: first capitalized multi-char token not in keywords."""
    for match in re.finditer(r"\b[A-Z][a-zA-Z0-9_.-]{2,}\b", sentence):
        token = match.group(0)
        if token.lower() not in {k for k in keywords}:
            return token
    return keywords[0] if keywords else "unknown"


def detect_conflicts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect numeric disagreements about the same entity across sources."""
    conflicts: list[dict[str, Any]] = []
    by_entity: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        by_entity.setdefault(str(fact.get("entity") or "unknown"), []).append(fact)
    for entity, group in by_entity.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if str(a.get("source_url")) == str(b.get("source_url")):
                    continue
                nums_a = re.findall(r"\d[\d.,]*", str(a.get("claim", "")))
                nums_b = re.findall(r"\d[\d.,]*", str(b.get("claim", "")))
                if nums_a and nums_b and set(nums_a).isdisjoint(nums_b):
                    conflicts.append({
                        "entity": entity,
                        "sources": [a.get("source_url"), b.get("source_url")],
                        "claims": [a.get("fact_id"), b.get("fact_id")],
                    })
    return conflicts[:20]


def _corroborate(facts: list[dict[str, Any]]) -> None:
    """Boost confidence of claims corroborated by 2+ distinct sources."""
    seen: dict[str, set[str]] = {}
    for fact in facts:
        normalized = re.sub(r"[^a-z0-9 ]", "", str(fact.get("claim", "")).lower())[:200]
        seen.setdefault(normalized, set()).add(str(fact.get("source_url")))
    for fact in facts:
        normalized = re.sub(r"[^a-z0-9 ]", "", str(fact.get("claim", "")).lower())[:200]
        if len(seen.get(normalized, set())) >= 2:
            fact["confidence"] = round(min(0.95, float(fact.get("confidence", 0.5)) + 0.1), 3)
            fact["corroborated"] = True


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


async def _browser_available() -> bool:
    """True only when a browser session is ALREADY running (research must not
    launch a browser as a side effect)."""
    try:
        from core.browser_manager import BrowserManager
        return bool(BrowserManager.instance()._started)
    except Exception:
        return False


async def do_browser_research(question: str, max_pages: int = 3, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    """Run bounded browser research and return an evidence-backed report.

    Without a running browser backend this returns a truthful empty report
    rather than pretending to have browsed.
    """
    question = str(question or "")
    plan = _create_plan(question)
    if max_pages is None or int(max_pages) <= 0 or not question:
        return _synthesize_report(question, [], [])

    if not await _browser_available():
        logger.info("browser research skipped: no running browser session")
        return _synthesize_report(question, [], [])

    from core.tools.browser_tools import (
        do_browser_extract,
        do_browser_navigate,
        do_browser_search,
    )

    queries = _get_queries(plan) or [question]
    facts: list[dict[str, Any]] = []
    sources: list[str] = []
    errors: list[str] = []

    try:
        search_result = await asyncio.wait_for(
            do_browser_search(query=queries[0], session_id=session_id),
            timeout=_SEARCH_TIMEOUT_S,
        )
    except Exception as exc:
        search_result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    if search_result.get("status") != "ok":
        errors.append(f"search failed: {search_result.get('error')}")
        report = _synthesize_report(question, [], [])
        report["errors"] = errors
        return report

    links = _extract_result_links(search_result)
    preferred_host = _pick_search_engine(question)
    keywords = _keywords(question)

    opened = 0
    for link in links:
        if opened >= int(max_pages):
            break
        href = str(link.get("href") or "")
        if not href.startswith("http") or href.rstrip("/") in {s.rstrip("/") for s in sources}:
            continue
        try:
            nav = await asyncio.wait_for(
                do_browser_navigate(href, session_id=session_id),
                timeout=_PAGE_TIMEOUT_S,
            )
            if nav.get("status") != "ok":
                errors.append(f"open failed: {href}: {nav.get('error')}")
                continue
            extract = await asyncio.wait_for(
                do_browser_extract(selector="body", max_chars=_MAX_PAGE_CHARS, session_id=session_id),
                timeout=_PAGE_TIMEOUT_S,
            )
            if extract.get("status") != "ok":
                errors.append(f"extract failed: {href}: {extract.get('error')}")
                continue
            page_text = str(extract.get("result", {}).get("text") or "")
            page_facts = _extract_facts(page_text, href, keywords)
            facts.extend(page_facts)
            sources.append(href)
            opened += 1
        except asyncio.TimeoutError:
            errors.append(f"timeout: {href}")
        except Exception as exc:
            errors.append(f"{href}: {type(exc).__name__}: {exc}")

    _corroborate(facts)
    conflicts = detect_conflicts(facts)
    report = _synthesize_report(question, facts, sources)
    if conflicts:
        report["conflicts"] = conflicts
        report["recommendations"] = report["recommendations"] or [
            "Sources disagree on some figures; verify against an authoritative source."
        ]
    if errors:
        report["errors"] = errors[:10]
    report["search_engine"] = preferred_host
    return report


async_do_browser_research = do_browser_research
