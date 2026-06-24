"""core/routes/research.py — REST API for Research Memory.

Exposes FactStore, FactReasoner, and FactSynthesizer as HTTP endpoints
for the Research Explorer UI.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.research.models import Fact
from core.research.reasoner import FactReasoner
from core.research.storage import FactStore
from core.research.synthesizer import FactSynthesizer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["Research"])

# ── Singletons ──────────────────────────────────────────────────────────────

_store: FactStore | None = None


def _get_store() -> FactStore:
    global _store
    if _store is None:
        _store = FactStore()
    return _store


# ── Response models ─────────────────────────────────────────────────────────


class FactResponse(BaseModel):
    fact_id: str
    source_url: str
    claim: str
    confidence: float
    category: str
    tags: list[str] = []
    timestamp: str | None = None
    activity_id: str | None = None
    node_id: str | None = None
    metadata: dict[str, Any] = {}


class ResearchSession(BaseModel):
    activity_id: str
    fact_count: int
    sources: list[str]
    categories: list[str]
    avg_confidence: float
    first_fact_at: str | None = None
    last_fact_at: str | None = None


class SessionDetail(BaseModel):
    session: ResearchSession
    facts: list[FactResponse]
    contradictions: list[dict[str, Any]] = []
    agreements: list[dict[str, Any]] = []
    syntheses: list[str] = []


class ContradictionResult(BaseModel):
    entity: str
    attribute: str
    values: list[str]
    sources: list[str]
    confidence: float = 1.0
    summary: str = ""


class ResearchSearchRequest(BaseModel):
    query: str
    limit: int = 20


class ResearchStatistics(BaseModel):
    total_facts: int = 0
    fact_count_by_category: dict[str, int] = {}
    fact_count_by_source: dict[str, int] = {}
    total_sessions: int = 0


# ── Helpers ─────────────────────────────────────────────────────────────────


def _fact_to_response(f: Fact) -> FactResponse:
    return FactResponse(
        fact_id=f.fact_id,
        source_url=f.source_url,
        claim=f.claim,
        confidence=f.confidence,
        category=f.category,
        tags=f.tags,
        timestamp=f.timestamp.isoformat() if f.timestamp else None,
        activity_id=f.activity_id,
        node_id=f.node_id,
        metadata=f.metadata,
    )


def _build_sessions(store: FactStore) -> list[ResearchSession]:
    """Derive research sessions by grouping facts by activity_id."""
    all_facts = store.get_all_facts(limit=5000)
    groups: dict[str, list[Fact]] = {}
    for f in all_facts:
        aid = f.activity_id or "__unassigned__"
        if aid not in groups:
            groups[aid] = []
        groups[aid].append(f)

    sessions = []
    for aid, facts in groups.items():
        sources = sorted({f.source_url for f in facts})
        categories = sorted({f.category for f in facts})
        avg_conf = sum(f.confidence for f in facts) / max(len(facts), 1)
        timestamps = [f.timestamp for f in facts if f.timestamp]
        sessions.append(ResearchSession(
            activity_id=aid,
            fact_count=len(facts),
            sources=sources,
            categories=categories,
            avg_confidence=round(avg_conf, 3),
            first_fact_at=min(timestamps).isoformat() if timestamps else None,
            last_fact_at=max(timestamps).isoformat() if timestamps else None,
        ))
    sessions.sort(key=lambda s: s.last_fact_at or "", reverse=True)
    return sessions


# ── Sessions ────────────────────────────────────────────────────────────────


@router.get("/sessions")
def list_sessions(limit: int = Query(50, ge=1, le=500)) -> dict:
    sessions = _build_sessions(_get_store())
    return {
        "sessions": sessions[:limit],
        "total": len(sessions),
    }


@router.get("/sessions/{activity_id}")
def get_session(activity_id: str) -> SessionDetail:
    store = _get_store()
    facts = store.get_facts_by_activity(activity_id)
    if not facts:
        raise HTTPException(status_code=404, detail="No research session found for this activity")

    sources = sorted({f.source_url for f in facts})
    categories = sorted({f.category for f in facts})
    avg_conf = sum(f.confidence for f in facts) / max(len(facts), 1)
    timestamps = [f.timestamp for f in facts if f.timestamp]

    session = ResearchSession(
        activity_id=activity_id,
        fact_count=len(facts),
        sources=sources,
        categories=categories,
        avg_confidence=round(avg_conf, 3),
        first_fact_at=min(timestamps).isoformat() if timestamps else None,
        last_fact_at=max(timestamps).isoformat() if timestamps else None,
    )

    # Contradictions + agreements via Reasoner
    contradictions: list[dict[str, Any]] = []
    agreements: list[dict[str, Any]] = []
    syntheses: list[str] = []

    if len(facts) >= 2:
        try:
            comparison = FactReasoner().analyze(facts)
            for c in comparison.contradictions:
                contradictions.append({
                    "entity": c.entity,
                    "attribute": c.attribute,
                    "values": c.values,
                    "sources": [f.source_url[:60] for f in c.facts],
                    "confidence": c.confidence,
                    "summary": c.summary(),
                })
            for a in comparison.agreements:
                agreements.append({
                    "entity": a.entity,
                    "attribute": a.attribute,
                    "value": a.value,
                    "sources": [f.source_url[:60] for f in a.facts],
                    "confidence": a.confidence,
                    "summary": a.summary(),
                })
            if comparison.contradictions or comparison.agreements:
                report = FactSynthesizer().synthesize(
                    topic=session.sources[0] if session.sources else "Research",
                    facts=facts,
                    comparison=comparison,
                )
                syntheses = report.recommendations or [
                    f"Sources: {len(report.sources_consulted)}",
                    f"Total facts: {report.total_facts}",
                    f"Overall confidence: {report.overall_confidence:.0%}",
                ]
        except Exception as e:
            logger.debug("Reasoner/Synthesizer error: %s", e)

    return SessionDetail(
        session=session,
        facts=[_fact_to_response(f) for f in facts],
        contradictions=contradictions,
        agreements=agreements,
        syntheses=syntheses,
    )


# ── Facts ───────────────────────────────────────────────────────────────────


@router.get("/facts")
def list_facts(
    category: str | None = Query(None, description="Filter by category"),
    source_url: str | None = Query(None, description="Filter by source URL"),
    activity_id: str | None = Query(None, description="Filter by activity"),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    store = _get_store()
    if activity_id:
        facts = store.get_facts_by_activity(activity_id)
    elif source_url:
        facts = store.get_facts_by_source(source_url)
    elif category:
        facts = store.get_facts_by_category(category, limit=limit)
    else:
        facts = store.get_all_facts(limit=limit)
    return {
        "facts": [_fact_to_response(f) for f in facts],
        "total": len(facts),
    }


@router.get("/facts/{fact_id}")
def get_fact(fact_id: str) -> FactResponse:
    fact = _get_store().get_fact(fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    return _fact_to_response(fact)


@router.post("/search")
def search_facts(req: ResearchSearchRequest) -> dict:
    facts = _get_store().search_facts(req.query, limit=req.limit)
    return {
        "facts": [_fact_to_response(f) for f in facts],
        "total": len(facts),
        "query": req.query,
    }


# ── Statistics ──────────────────────────────────────────────────────────────


@router.get("/statistics", response_model=ResearchStatistics)
def get_research_statistics() -> ResearchStatistics:
    store = _get_store()
    sessions = _build_sessions(store)
    return ResearchStatistics(
        total_facts=store.count_facts(),
        fact_count_by_category=store.count_by_category(),
        fact_count_by_source=store.count_by_source(),
        total_sessions=len(sessions),
    )


# ── Contradictions (cross-session) ──────────────────────────────────────────


@router.get("/contradictions")
def list_contradictions(limit: int = Query(50, ge=1, le=500)) -> dict:
    store = _get_store()
    all_facts = store.get_all_facts(limit=2000)
    results: list[ContradictionResult] = []

    if len(all_facts) >= 2:
        try:
            comparison = FactReasoner().analyze(all_facts)
            for c in comparison.contradictions:
                results.append(ContradictionResult(
                    entity=c.entity,
                    attribute=c.attribute,
                    values=c.values,
                    sources=[f.source_url[:80] for f in c.facts],
                    confidence=c.confidence,
                    summary=c.summary(),
                ))
        except Exception as e:
            logger.debug("Cross-session reasoner error: %s", e)

    return {
        "contradictions": results[:limit],
        "total": len(results),
    }
