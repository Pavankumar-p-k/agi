from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class ScoreBreakdown:
    """Breakdown of a provider's score during routing."""

    provider_id: str
    priority_score: float = 0.0
    historical_score: float = 0.0
    benchmark_score: float = 0.0
    calibration_adjustment: float = 0.0
    total_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "priority_score": self.priority_score,
            "historical_score": self.historical_score,
            "benchmark_score": self.benchmark_score,
            "calibration_adjustment": self.calibration_adjustment,
            "total_score": self.total_score,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScoreBreakdown:
        return cls(
            provider_id=d["provider_id"],
            priority_score=d.get("priority_score", 0.0),
            historical_score=d.get("historical_score", 0.0),
            benchmark_score=d.get("benchmark_score", 0.0),
            calibration_adjustment=d.get("calibration_adjustment", 0.0),
            total_score=d.get("total_score", 0.0),
        )


@dataclass
class RoutingDecision:
    """Record of a single routing decision made by the ProviderRouter."""

    decision_id: str = field(default_factory=lambda: f"dec_{uuid4().hex[:12]}")
    goal: str = ""
    capability: str = ""
    task: dict[str, Any] = field(default_factory=dict)
    selected_provider: str = ""
    candidate_scores: list[ScoreBreakdown] = field(default_factory=list)
    excluded_providers: list[str] = field(default_factory=list)
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "goal": self.goal,
            "capability": self.capability,
            "task": self.task,
            "selected_provider": self.selected_provider,
            "candidate_scores": [s.to_dict() for s in self.candidate_scores],
            "excluded_providers": self.excluded_providers,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RoutingDecision:
        return cls(
            decision_id=d.get("decision_id", ""),
            goal=d.get("goal", ""),
            capability=d.get("capability", ""),
            task=d.get("task", {}),
            selected_provider=d.get("selected_provider", ""),
            candidate_scores=[ScoreBreakdown.from_dict(s) for s in d.get("candidate_scores", [])],
            excluded_providers=d.get("excluded_providers", []),
            timestamp=d.get("timestamp", 0.0),
        )


@dataclass
class RoutingOutcome:
    """Outcome of a routed step execution."""

    outcome_id: str = field(default_factory=lambda: f"out_{uuid4().hex[:12]}")
    decision_id: str = ""
    success: bool = False
    duration_ms: float = 0.0
    quality_score: float = 0.0
    cost: float = 0.0
    error: str = ""
    retries: int = 0
    replan_level: int = 0
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "decision_id": self.decision_id,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "quality_score": self.quality_score,
            "cost": self.cost,
            "error": self.error,
            "retries": self.retries,
            "replan_level": self.replan_level,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RoutingOutcome:
        return cls(
            outcome_id=d.get("outcome_id", ""),
            decision_id=d.get("decision_id", ""),
            success=d.get("success", False),
            duration_ms=d.get("duration_ms", 0.0),
            quality_score=d.get("quality_score", 0.0),
            cost=d.get("cost", 0.0),
            error=d.get("error", ""),
            retries=d.get("retries", 0),
            replan_level=d.get("replan_level", 0),
            timestamp=d.get("timestamp", 0.0),
        )

    @property
    def outcome_score(self) -> float:
        """Composite outcome quality (0.0–1.0).

        Weighted from success (0.5), quality (0.3), and
        normalized duration (0.2, only if successful).
        Replanning penalty: -0.1 per level.
        """
        score = 0.0
        if self.success:
            score += 0.5
            dur_factor = max(0.0, 1.0 - self.duration_ms / 300000.0)
            score += dur_factor * 0.2
        score += self.quality_score * 0.3
        score -= self.replan_level * 0.1
        return max(0.0, min(1.0, score))


@dataclass
class CalibrationEntry:
    """Calibration adjustment for a (provider_id, capability) pair."""

    entry_id: str = field(default_factory=lambda: f"cal_{uuid4().hex[:12]}")
    provider_id: str = ""
    capability: str = ""
    adjustment: float = 0.0
    confidence: float = 0.0
    evidence_count: int = 0
    last_updated: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "provider_id": self.provider_id,
            "capability": self.capability,
            "adjustment": self.adjustment,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "last_updated": self.last_updated,
        }
