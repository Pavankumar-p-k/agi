"""Opportunity Discovery Engine — data models for improvement opportunity candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OpportunitySource(str, Enum):
    """Where the opportunity was discovered from."""

    BOTTLENECK = "bottleneck"
    CEILING = "ceiling"
    EXPERIMENT = "experiment"
    PRINCIPLE = "principle"


class OpportunityStatus(str, Enum):
    """Lifecycle state of an opportunity candidate."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


@dataclass
class Opportunity:
    """A discovered improvement opportunity with scored dimensions.

    The core formula:
        opportunity_score = bottleneck_impact × improvement_headroom
                          × success_probability × confidence × calibration_accuracy

    Each dimension is 0.0–1.0, making the product a conservative estimate
    that penalizes weakness in any single factor.
    """

    id: str
    target_system: str
    improvement_description: str
    source: OpportunitySource
    bottleneck_impact: float
    improvement_headroom: float
    success_probability: float
    confidence: float
    opportunity_score: float
    rationale: str
    calibration_accuracy: float = 1.0
    evidence: list[str] = field(default_factory=list)
    status: OpportunityStatus = OpportunityStatus.OPEN
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "target_system": self.target_system,
            "improvement_description": self.improvement_description,
            "source": self.source.value,
            "bottleneck_impact": round(self.bottleneck_impact, 3),
            "improvement_headroom": round(self.improvement_headroom, 3),
            "success_probability": round(self.success_probability, 3),
            "confidence": round(self.confidence, 3),
            "calibration_accuracy": round(self.calibration_accuracy, 3),
            "opportunity_score": round(self.opportunity_score, 3),
            "rationale": self.rationale,
            "evidence": self.evidence[:5],
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def short_summary(self) -> str:
        cal = f" cal={self.calibration_accuracy:.2f}" if self.calibration_accuracy != 1.0 else ""
        return (
            f"[{self.opportunity_score:.2f}{cal}] {self.target_system}: "
            f"{self.improvement_description[:60]}"
        )
