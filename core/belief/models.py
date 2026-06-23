"""Belief Quality Engine — data models for evidence quality tracking.

The core insight: confidence should not be a single heuristic number.
It should be a product of independently measurable dimensions:

    confidence = source_quality × evidence_strength × accuracy × freshness
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    """Categories of knowledge sources for reliability tracking."""

    RESEARCH_URL = "research_url"
    ACTIVITY = "activity"
    TOOL = "tool"
    AGENT = "agent"
    EXPERIENCE = "experience"
    EXPERIMENT = "experiment"
    PATTERN_FAILURE_MEMORY = "pattern_failure_memory"
    HUMAN_FEEDBACK = "human_feedback"


class BeliefCategory(str, Enum):
    """Categories of beliefs that map to existing KnowledgeItem categories."""

    PATTERN = "pattern"
    PRINCIPLE = "principle"
    HEURISTIC = "heuristic"
    FACTOID = "factoid"
    WARNING = "warning"
    RESEARCH_FACT = "research_fact"


@dataclass
class SourceProfile:
    """Tracks the reliability of a knowledge source over time.

    source_id: unique identifier (URL, activity_id, tool name)
    source_type: category of source
    reliability_score: 0.0–1.0 — overall correctness rate
    domain_scores: per-domain reliability breakdown
    total_references: how many times this source has contributed evidence
    correct_references: how many of those were later confirmed correct
    contradictory_references: how many times this source contradicted others
    first_seen: when this source first appeared
    last_seen: most recent reference
    """

    source_id: str
    source_type: SourceType
    reliability_score: float = 0.5
    domain_scores: dict[str, float] = field(default_factory=dict)
    total_references: int = 0
    correct_references: int = 0
    contradictory_references: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "reliability_score": round(self.reliability_score, 3),
            "domain_scores": {k: round(v, 3) for k, v in self.domain_scores.items()},
            "total_references": self.total_references,
            "correct_references": self.correct_references,
            "contradictory_references": self.contradictory_references,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SourceProfile:
        return cls(
            source_id=d["source_id"],
            source_type=SourceType(d["source_type"]),
            reliability_score=d.get("reliability_score", 0.5),
            domain_scores=d.get("domain_scores", {}),
            total_references=d.get("total_references", 0),
            correct_references=d.get("correct_references", 0),
            contradictory_references=d.get("contradictory_references", 0),
            first_seen=_parse_dt(d.get("first_seen")),
            last_seen=_parse_dt(d.get("last_seen")),
        )


@dataclass
class AccuracyRecord:
    """Tracks whether a prediction or belief was correct.

    belief_id: what was predicted/believed
    domain: context domain
    category: belief category
    predicted_value: the predicted outcome (0.0–1.0)
    actual_value: what actually happened (0.0–1.0)
    error: absolute difference
    timestamp: when this was recorded
    source_id: optional link to the source that produced this belief
    """

    record_id: str
    belief_id: str
    domain: str
    category: str
    predicted_value: float
    actual_value: float
    error: float
    timestamp: datetime | None = None
    source_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "belief_id": self.belief_id,
            "domain": self.domain,
            "category": self.category,
            "predicted_value": round(self.predicted_value, 3),
            "actual_value": round(self.actual_value, 3),
            "error": round(self.error, 3),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source_id": self.source_id,
        }


@dataclass
class DomainAccuracyMetrics:
    """Aggregated accuracy metrics for a specific domain."""

    domain: str
    total_records: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0
    mean_error: float = 0.0
    contradiction_rate: float = 0.0
    last_updated: datetime | None = None


@dataclass
class DecomposedConfidence:
    """A confidence value broken into its constituent quality dimensions.

    This enables explainability: "confidence is 0.74 because:
      - source_quality: 0.85 (this source is reliable)
      - evidence_strength: 0.92 (24 data points)
      - accuracy: 0.82 (domain-level prediction accuracy)
      - freshness: 0.95 (evidence is recent)
    """

    overall: float = 0.5
    source_quality: float = 0.5
    evidence_strength: float = 0.5
    accuracy: float = 0.5
    freshness: float = 1.0
    consensus: float = 1.0
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, float]:
        return {
            "overall": round(self.overall, 3),
            "source_quality": round(self.source_quality, 3),
            "evidence_strength": round(self.evidence_strength, 3),
            "accuracy": round(self.accuracy, 3),
            "freshness": round(self.freshness, 3),
            "consensus": round(self.consensus, 3),
            **{f"raw_{k}": round(v, 3) for k, v in self.components.items()},
        }


@dataclass
class BeliefQualityRequest:
    """Input to the QualityEngine for computing a decomposed confidence.

    All fields optional — the engine fills missing dimensions with defaults.
    """

    source_id: str | None = None
    source_type: SourceType | None = None
    evidence_count: int = 0
    category: BeliefCategory = BeliefCategory.HEURISTIC
    domain: str | None = None
    created_at: datetime | None = None
    last_validated: datetime | None = None
    current_confidence: float | None = None
    supporting_sources: list[str] | None = None
    contradicting_sources: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _parse_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None
