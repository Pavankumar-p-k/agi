"""Belief Quality Engine data models.

Real implementations for the Phase 16.0 belief-quality subsystem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


class SourceType(str, Enum):
    """Where a piece of evidence originated."""

    RESEARCH_URL = "research_url"
    ACTIVITY = "activity"
    HUMAN_FEEDBACK = "human_feedback"
    TOOL = "tool"
    AGENT = "agent"


class BeliefCategory(str, Enum):
    """Classification of a belief."""

    PATTERN = "pattern"
    PRINCIPLE = "principle"
    WARNING = "warning"
    HEURISTIC = "heuristic"


@dataclass
class SourceProfile:
    """Reliability profile for a single evidence source."""

    source_id: str
    source_type: SourceType = SourceType.TOOL
    reliability_score: float = 0.5
    domain_scores: Dict[str, float] = field(default_factory=dict)
    total_references: int = 0
    correct_references: int = 0
    contradictory_references: int = 0
    first_seen: datetime = field(default_factory=_utcnow)
    last_updated: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        source_type = self.source_type
        if isinstance(source_type, SourceType):
            source_type = source_type.value
        return {
            "source_id": self.source_id,
            "source_type": source_type,
            "reliability_score": self.reliability_score,
            "domain_scores": dict(self.domain_scores),
            "total_references": self.total_references,
            "correct_references": self.correct_references,
            "contradictory_references": self.contradictory_references,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceProfile":
        source_type = data.get("source_type", SourceType.TOOL)
        if not isinstance(source_type, SourceType):
            try:
                source_type = SourceType(source_type)
            except ValueError:
                source_type = SourceType.TOOL
        return cls(
            source_id=data.get("source_id", ""),
            source_type=source_type,
            reliability_score=float(data.get("reliability_score", 0.5)),
            domain_scores=dict(data.get("domain_scores", {}) or {}),
            total_references=int(data.get("total_references", 0)),
            correct_references=int(data.get("correct_references", 0)),
            contradictory_references=int(data.get("contradictory_references", 0)),
            first_seen=_parse_dt(data.get("first_seen")) or _utcnow(),
            last_updated=_parse_dt(data.get("last_updated")) or _utcnow(),
        )


@dataclass
class DecomposedConfidence:
    """Confidence split into its contributing dimensions."""

    overall: float = 0.5
    source_quality: float = 0.5
    evidence_strength: float = 0.5
    accuracy: float = 0.5
    freshness: float = 1.0
    consensus: float = 1.0
    components: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "overall": self.overall,
            "source_quality": self.source_quality,
            "evidence_strength": self.evidence_strength,
            "accuracy": self.accuracy,
            "freshness": self.freshness,
            "consensus": self.consensus,
            "raw_evidence_count": self.components.get("evidence_count", 0.0),
        }
        for key, value in self.components.items():
            data.setdefault(key, value)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecomposedConfidence":
        components = {
            k: v
            for k, v in data.items()
            if k not in {
                "overall",
                "source_quality",
                "evidence_strength",
                "accuracy",
                "freshness",
                "consensus",
            }
        }
        if "raw_evidence_count" in data and "evidence_count" not in components:
            components["evidence_count"] = data["raw_evidence_count"]
        return cls(
            overall=float(data.get("overall", 0.5)),
            source_quality=float(data.get("source_quality", 0.5)),
            evidence_strength=float(data.get("evidence_strength", 0.5)),
            accuracy=float(data.get("accuracy", 0.5)),
            freshness=float(data.get("freshness", 1.0)),
            consensus=float(data.get("consensus", 1.0)),
            components=components,
        )


@dataclass
class AccuracyRecord:
    """A single prediction-vs-outcome observation."""

    record_id: str
    belief_id: str = ""
    domain: str = ""
    category: str = ""
    predicted_value: float = 0.0
    actual_value: float = 0.0
    error: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "belief_id": self.belief_id,
            "domain": self.domain,
            "category": self.category,
            "predicted_value": self.predicted_value,
            "actual_value": self.actual_value,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccuracyRecord":
        return cls(
            record_id=data.get("record_id", ""),
            belief_id=data.get("belief_id", ""),
            domain=data.get("domain", ""),
            category=data.get("category", ""),
            predicted_value=float(data.get("predicted_value", 0.0)),
            actual_value=float(data.get("actual_value", 0.0)),
            error=float(data.get("error", 0.0)),
        )


@dataclass
class DomainAccuracyMetrics:
    """Aggregate accuracy for a domain."""

    domain: str = ""
    total_records: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "total_records": self.total_records,
            "correct_predictions": self.correct_predictions,
            "accuracy": self.accuracy,
        }


@dataclass
class BeliefQualityRequest:
    """Input to the QualityEngine confidence computation."""

    evidence_count: int = 0
    category: Optional[str] = None
    domain: str = ""
    source_id: Optional[str] = None
    created_at: Optional[datetime] = None
    last_validated: Optional[datetime] = None
    current_confidence: Optional[float] = None
    supporting_sources: Optional[List[str]] = None
    contradicting_sources: Optional[List[str]] = None
