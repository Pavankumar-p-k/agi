"""Phase 12 — Strategic Reasoning data models.

Core types:
  Strategy          — a candidate approach to achieve a goal
  Prediction        — expected outcomes for a strategy
  StrategyDecision  — the chosen strategy with full context (stored for learning)
  EvidenceBundle    — historical evidence for a goal (produced by MemoryAdapter)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class StrategyTag(str, enum.Enum):
    """High-level category labels for strategies."""
    MVP = "mvp"
    FEATURE_COMPLETE = "feature_complete"
    QUALITY_FIRST = "quality_first"
    RESEARCH_DRIVEN = "research_driven"
    SAFE = "safe"
    AMBITIOUS = "ambitious"
    ITERATIVE = "iterative"


@dataclass
class Prediction:
    """Expected outcome of executing a strategy."""
    success_probability: float = 0.5        # 0.0–1.0
    estimated_duration_days: float = 14.0   # in days
    estimated_risk: float = 0.3             # 0.0 (safe) – 1.0 (risky)
    estimated_effort: float = 5.0           # relative units (person-days)
    confidence: float = 0.3                 # 0.0–1.0 (how much evidence supports this)
    evidence_count: int = 0                 # number of past similar cases

    def to_dict(self) -> dict[str, Any]:
        return {
            "success_probability": round(self.success_probability, 3),
            "estimated_duration_days": round(self.estimated_duration_days, 1),
            "estimated_risk": round(self.estimated_risk, 3),
            "estimated_effort": round(self.estimated_effort, 1),
            "confidence": round(self.confidence, 3),
            "evidence_count": self.evidence_count,
        }


@dataclass
class EvidenceBundle:
    """Aggregated historical evidence for a goal, produced by MemoryAdapter.

    The predictor blends this with heuristic estimates to produce
    evidence-aware predictions.

    Phase 12.6: avg_similarity reflects the mean similarity score of the
    top-K activities that contributed to this bundle. Higher values mean
    the evidence is more relevant to the current goal.
    """
    sample_size: int = 0
    avg_duration_days: float = 0.0
    duration_std: float = 0.0
    success_rate: float = 0.0
    avg_similarity: float = 0.0
    common_failures: list[str] = field(default_factory=list)
    similar_activities: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "avg_duration_days": round(self.avg_duration_days, 1),
            "duration_std": round(self.duration_std, 2),
            "success_rate": round(self.success_rate, 3),
            "avg_similarity": round(self.avg_similarity, 3),
            "common_failures": self.common_failures[:5],
            "similar_activities": self.similar_activities[:5],
            "confidence": round(self.confidence, 3),
        }


@dataclass
class Strategy:
    """A candidate approach for achieving a goal.
    
    The generator produces these. The predictor enriches them with predictions.
    The evaluator scores them. The selector picks one.
    """
    name: str                                # short label, e.g. "MVP-first"
    description: str                         # what this strategy entails
    goal: str                                # the goal this strategy addresses
    tags: list[StrategyTag] = field(default_factory=list)
    prediction: Prediction | None = None     # set by predictor
    reasoning: str = ""                      # why this strategy exists
    
    def to_dict(self, include_prediction: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "description": self.description[:200],
            "goal": self.goal[:100],
            "tags": [t.value for t in self.tags],
        }
        if include_prediction and self.prediction:
            d["prediction"] = self.prediction.to_dict()
        return d


@dataclass
class StrategyDecision:
    """Record of a strategic choice. Stored for learning.
    
    After execution, actual_outcome is recorded so the system can
    compare predictions to reality and improve.
    """
    decision_id: str
    goal: str
    timestamp: datetime
    strategies_considered: list[Strategy]    # all candidates with predictions
    chosen_strategy: Strategy                # the selected one
    confidence: float                        # 0.0–1.0

    # Populated after execution
    actual_success: bool | None = None
    actual_duration_days: float | None = None
    actual_risk_realized: float | None = None  # actual issues encountered

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def prediction_error_duration(self) -> float | None:
        """How far off the duration estimate was (ratio)."""
        if (self.chosen_strategy.prediction is None
                or self.actual_duration_days is None):
            return None
        predicted = self.chosen_strategy.prediction.estimated_duration_days
        if predicted == 0:
            return None
        return (self.actual_duration_days - predicted) / predicted

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "goal": self.goal[:100],
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "strategies_considered": [
                s.to_dict() for s in self.strategies_considered
            ],
            "chosen": self.chosen_strategy.to_dict(),
            "confidence": round(self.confidence, 3),
            "actual_success": self.actual_success,
            "prediction_error_duration": round(self.prediction_error_duration, 3)
                if self.prediction_error_duration is not None else None,
        }
