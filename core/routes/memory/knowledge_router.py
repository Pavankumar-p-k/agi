"""core/routes/knowledge.py — REST API for Knowledge Store + Pattern Failures.

Exposes KnowledgeStore (knowledge items + experiences) and
PatternFailureMemory as HTTP endpoints for the Knowledge Explorer UI.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.long_term_memory.models import KnowledgeItem, KnowledgeQuery
from core.long_term_memory.store import KnowledgeStore
from core.pattern_failure_memory import PatternFailureMemory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])

# ── Singletons ──────────────────────────────────────────────────────────────

_store: KnowledgeStore | None = None
_pfm: PatternFailureMemory | None = None


def _get_store() -> KnowledgeStore:
    global _store
    if _store is None:
        _store = KnowledgeStore()
    return _store


def _get_pfm() -> PatternFailureMemory:
    global _pfm
    if _pfm is None:
        _pfm = PatternFailureMemory()
    return _pfm


# ── Response models ─────────────────────────────────────────────────────────


class KnowledgeItemResponse(BaseModel):
    knowledge_id: str
    category: str
    claim: str
    confidence: float
    evidence_count: int
    source_activity_ids: list[str] = []
    source_pattern_keys: list[str] = []
    tags: list[str] = []
    created_at: str | None = None
    last_validated: str | None = None
    metadata: dict[str, Any] = {}


class ExperienceResponse(BaseModel):
    activity_id: str
    goal: str
    domain: str
    status: str
    node_count: int
    agent_ids: list[str] = []
    tools_used: list[str] = []
    artifacts_produced: list[str] = []
    success: bool = True
    error_summary: str | None = None
    duration_seconds: float | None = None
    outcome_quality: float | None = None
    created_at: str | None = None


class KnowledgeStatisticsResponse(BaseModel):
    total_knowledge_items: int = 0
    total_experiences: int = 0
    knowledge_by_category: dict[str, int] = {}
    domains: list[str] = []
    total_patterns: int = 0
    total_failures: int = 0


class PatternResponse(BaseModel):
    pattern: str
    regex: str
    count: int
    first_seen: str = ""
    last_seen: str = ""
    exemplar: str = ""
    best_strategy: str | None = None
    strategies: dict[str, dict[str, Any]] = {}


class FailureResponse(BaseModel):
    pattern: str
    fix_strategy: str
    count: int
    last_seen: str = ""


class SearchRequest(BaseModel):
    query: str
    limit: int = 20


# ── Helpers ─────────────────────────────────────────────────────────────────


def _k_to_response(k: KnowledgeItem) -> KnowledgeItemResponse:
    return KnowledgeItemResponse(
        knowledge_id=k.knowledge_id,
        category=k.category,
        claim=k.claim,
        confidence=k.confidence,
        evidence_count=k.evidence_count,
        source_activity_ids=k.source_activity_ids,
        source_pattern_keys=k.source_pattern_keys,
        tags=k.tags,
        created_at=k.created_at.isoformat() if k.created_at else None,
        last_validated=k.last_validated.isoformat() if k.last_validated else None,
        metadata=k.metadata,
    )


def _exp_to_response(e: Any) -> ExperienceResponse:
    return ExperienceResponse(
        activity_id=e.activity_id,
        goal=e.goal,
        domain=e.domain,
        status=e.status,
        node_count=e.node_count,
        agent_ids=e.agent_ids,
        tools_used=e.tools_used,
        artifacts_produced=e.artifacts_produced,
        success=e.success,
        error_summary=e.error_summary,
        duration_seconds=e.duration_seconds,
        outcome_quality=e.outcome_quality,
        created_at=e.created_at.isoformat() if e.created_at else None,
    )


# ── Knowledge Items ─────────────────────────────────────────────────────────


@router.get("")
def list_knowledge(
    category: str | None = Query(None, description="Filter by category (pattern, principle, heuristic, factoid, warning)"),
    tag: str | None = Query(None, description="Filter by tag"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    q = KnowledgeQuery(
        category=category,
        tag=tag,
        min_confidence=min_confidence,
        limit=limit,
    )
    items = _get_store().query_knowledge(q)
    return {
        "knowledge": [_k_to_response(k) for k in items],
        "total": len(items),
    }


@router.post("/search")
def search_knowledge(req: SearchRequest) -> dict:
    items = _get_store().search_knowledge(req.query, limit=req.limit)
    return {
        "knowledge": [_k_to_response(k) for k in items],
        "total": len(items),
        "query": req.query,
    }


@router.get("/{knowledge_id}")
def get_knowledge(knowledge_id: str) -> KnowledgeItemResponse:
    k = _get_store().get_knowledge(knowledge_id)
    if k is None:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return _k_to_response(k)


@router.get("/statistics", response_model=KnowledgeStatisticsResponse)
def get_knowledge_statistics() -> KnowledgeStatisticsResponse:
    store = _get_store()
    stats = store.get_statistics()
    pfm = _get_pfm()
    try:
        all_p = list(pfm._get_patterns().values()) if hasattr(pfm, '_get_patterns') else []
    except Exception:
        all_p = []
    patterns = [p for p in all_p if not _is_failure_pattern(p)]
    failures = [p for p in all_p if _is_failure_pattern(p)]
    return KnowledgeStatisticsResponse(
        total_knowledge_items=stats.get("total_knowledge_items", 0),
        total_experiences=stats.get("total_experiences", 0),
        knowledge_by_category=stats.get("knowledge_by_category", {}),
        domains=stats.get("domains", []),
        total_patterns=len(patterns),
        total_failures=len(failures),
    )


# ── Experiences ─────────────────────────────────────────────────────────────


@router.get("/experiences")
def list_experiences(
    domain: str | None = Query(None, description="Filter by domain"),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    store = _get_store()
    if domain:
        exps = store.get_experiences_by_domain(domain, limit=limit)
    else:
        exps = store.get_all_experiences(limit=limit)
    return {
        "experiences": [_exp_to_response(e) for e in exps],
        "total": len(exps),
    }


@router.get("/experiences/{activity_id}")
def get_experience(activity_id: str) -> ExperienceResponse:
    e = _get_store().get_experience(activity_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Experience not found")
    return _exp_to_response(e)


# ── Patterns ────────────────────────────────────────────────────────────────


@router.get("/patterns")
def list_patterns(limit: int = Query(50, ge=1, le=500)) -> dict:
    pfm = _get_pfm()
    try:
        raw = _enumerate_patterns(pfm)
        patterns = [p for p in raw if not _is_failure_key(p.pattern)]
    except Exception as e:
        logger.warning("Failed to list patterns: %s", e)
        patterns = []
    return {
        "patterns": [p.model_dump() if hasattr(p, 'model_dump') else p for p in patterns[:limit]],
        "total": len(patterns),
    }


@router.get("/failures")
def list_failures(limit: int = Query(50, ge=1, le=500)) -> dict:
    pfm = _get_pfm()
    try:
        failures = _enumerate_failures(pfm)
    except Exception as e:
        logger.warning("Failed to list failures: %s", e)
        failures = []
    return {
        "failures": [f.model_dump() if hasattr(f, 'model_dump') else f for f in failures[:limit]],
        "total": len(failures),
    }


# ── Helpers for pattern/failure enumeration ─────────────────────────────────


def _is_failure_key(pattern: str) -> bool:
    return pattern.startswith("FAILED:") or "FAILED" in pattern


def _is_failure_pattern(entry: Any) -> bool:
    return _is_failure_key(getattr(entry, "pattern", ""))


def _enumerate_patterns(pfm: PatternFailureMemory) -> list[PatternResponse]:
    """Extract all non-failure patterns from the PatternFailureMemory."""
    try:
        pfm._ensure_loaded()
    except AttributeError:
        pass
    entries = []
    if hasattr(pfm, '_patterns'):
        for key, entry in pfm._patterns.items():
            if _is_failure_key(key):
                continue
            best = entry.best_strategy() if hasattr(entry, 'best_strategy') else None
            strategies = {}
            if hasattr(entry, 'strategies'):
                for sname, sstats in entry.strategies.items():
                    if hasattr(sstats, 'success_count'):
                        strategies[sname] = {
                            "success_count": sstats.success_count,
                            "failure_count": sstats.failure_count,
                            "success_rate": sstats.success_rate,
                            "last_used": sstats.last_used,
                        }
                    else:
                        strategies[sname] = {"raw": str(sstats)}
            entries.append(PatternResponse(
                pattern=entry.pattern if hasattr(entry, 'pattern') else key,
                regex=entry.regex if hasattr(entry, 'regex') else "",
                count=getattr(entry, 'count', 1),
                first_seen=getattr(entry, 'first_seen', ""),
                last_seen=getattr(entry, 'last_seen', ""),
                exemplar=getattr(entry, 'exemplar', ""),
                best_strategy=best,
                strategies=strategies,
            ))
    return entries


def _enumerate_failures(pfm: PatternFailureMemory) -> list[FailureResponse]:
    """Extract failure entries from the PatternFailureMemory."""
    try:
        pfm._ensure_loaded()
    except AttributeError:
        pass
    failures = []
    if hasattr(pfm, '_patterns'):
        for key, entry in pfm._patterns.items():
            if not _is_failure_key(key):
                continue
            strategy = entry.fix_strategy if hasattr(entry, 'fix_strategy') else ""
            failures.append(FailureResponse(
                pattern=entry.pattern if hasattr(entry, 'pattern') else key,
                fix_strategy=strategy,
                count=getattr(entry, 'count', 1),
                last_seen=getattr(entry, 'last_seen', ""),
            ))
    return failures
