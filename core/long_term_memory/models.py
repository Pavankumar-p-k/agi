"""Long-Term Memory data models.

Four-layer condensation hierarchy:
  1000 Activities → 100 Experiences → 50 KnowledgeItems → 10 Principles
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.storage import SYSTEM_DB


@dataclass
class ExperienceSummary:
    """Condensed view of a completed activity for cross-activity pattern detection.

    Stores the essential shape of an activity without the full DAG.
    """

    activity_id: str
    goal: str
    domain: str                    # e.g., "android", "web", "research"
    status: str                    # COMPLETED | FAILED
    node_count: int
    agent_ids: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    artifacts_produced: list[str] = field(default_factory=list)
    success: bool = True
    error_summary: str | None = None
    duration_seconds: float | None = None
    outcome_quality: float | None = None  # 0.0–1.0
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "goal": self.goal,
            "domain": self.domain,
            "status": self.status,
            "node_count": self.node_count,
            "agent_ids": self.agent_ids,
            "tools_used": self.tools_used,
            "artifacts_produced": self.artifacts_produced,
            "success": self.success,
            "error_summary": self.error_summary,
            "duration_seconds": self.duration_seconds,
            "outcome_quality": self.outcome_quality,
        }


@dataclass
class KnowledgeItem:
    """A piece of durable knowledge extracted from multiple experiences.

    knowledge_id: unique identifier
    category: one of pattern, principle, heuristic, factoid, warning
    claim: what was learned (e.g., "payment features succeed on forge")
    confidence: 0.0–1.0 statistical confidence
    evidence_count: number of experiences supporting this
    source_activity_ids: activity IDs that contributed
    source_pattern_keys: PatternFailureMemory keys that contributed
    tags: for filtering
    last_validated: ISO datetime of most recent confirmation
    metadata: free-form
    """

    knowledge_id: str
    category: str                   # pattern | principle | heuristic | factoid | warning
    claim: str
    confidence: float = 0.5
    evidence_count: int = 1
    source_activity_ids: list[str] = field(default_factory=list)
    source_pattern_keys: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    last_validated: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "category": self.category,
            "claim": self.claim,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "source_activity_ids": self.source_activity_ids,
            "source_pattern_keys": self.source_pattern_keys,
            "tags": self.tags,
            "last_validated": self.last_validated.isoformat() if self.last_validated else None,
        }


@dataclass
class KnowledgeQuery:
    """Structured query against the knowledge store."""

    category: str | None = None
    tag: str | None = None
    min_confidence: float = 0.0
    min_evidence: int = 1
    limit: int = 20


UNIFIED_DB = SYSTEM_DB
