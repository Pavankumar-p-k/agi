"""Strategic Reasoning Layer data models (Phase 12)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional


class StrategyTag(str, Enum):
    """Tags describing the character of a strategy."""

    MVP = "mvp"
    SAFE = "safe"
    FAST = "fast"
    FEATURE_COMPLETE = "feature_complete"
    QUALITY_FIRST = "quality_first"
    RESEARCH_DRIVEN = "research_driven"
    BROAD_SURVEY = "broad_survey"
    DEEP_DIVE = "deep_dive"
    TARGETED = "targeted"
    MINIMAL_CHANGE = "minimal_change"
    INCREMENTAL = "incremental"
    FULL_REFACTOR = "full_refactor"
    EXPLORATORY = "exploratory"
    COMPARATIVE = "comparative"
    PROTOTYPE = "prototype"
    RISKY = "risky"
    THOROUGH = "thorough"

    @classmethod
    def _missing_(cls, value):
        value = str(value)
        member = str.__new__(cls, value)
        member._name_ = value.upper()
        member._value_ = value
        return member


def _tag_value(tag) -> str:
    return getattr(tag, "value", tag)


def _tag_values(tags) -> List[str]:
    return [_tag_value(t) for t in (tags or [])]


@dataclass
class Prediction:
    """Forecast for how a strategy will play out."""

    success_probability: float = 0.5
    estimated_duration_days: float = 7.0
    estimated_risk: float = 0.5
    estimated_effort: float = 5.0
    confidence: float = 0.3
    evidence_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def copy(self) -> "Prediction":
        return Prediction(**asdict(self))


@dataclass
class EvidenceBundle:
    """Aggregated historical evidence supporting a prediction."""

    sample_size: int = 0
    avg_duration_days: float = 0.0
    duration_std: float = 0.0
    success_rate: float = 0.0
    avg_similarity: float = 0.0
    common_failures: List[str] = field(default_factory=list)
    similar_activities: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Strategy:
    """A candidate approach to achieving a goal."""

    name: str
    description: str = ""
    goal: str = ""
    prediction: Optional[Prediction] = None
    tags: List[Any] = field(default_factory=list)

    def to_dict(self, include_prediction: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "goal": self.goal,
            "tags": _tag_values(self.tags),
        }
        if include_prediction:
            data["prediction"] = (
                self.prediction.to_dict() if self.prediction else None
            )
        return data


@dataclass
class StrategyDecision:
    """The outcome of evaluating and selecting a strategy."""

    decision_id: str
    goal: str
    timestamp: datetime
    strategies_considered: List[Strategy] = field(default_factory=list)
    chosen_strategy: Optional[Strategy] = None
    confidence: float = 0.0
    actual_success: Optional[bool] = None
    actual_duration_days: Optional[float] = None

    @property
    def prediction_error_duration(self) -> Optional[float]:
        if self.actual_duration_days is None:
            return None
        if self.chosen_strategy is None or self.chosen_strategy.prediction is None:
            return None
        predicted = self.chosen_strategy.prediction.estimated_duration_days
        if not predicted:
            return None
        return (self.actual_duration_days - predicted) / predicted

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "goal": self.goal,
            "timestamp": self.timestamp.isoformat(),
            "strategies_considered": [
                s.to_dict() for s in self.strategies_considered
            ],
            "chosen_strategy": (
                self.chosen_strategy.to_dict() if self.chosen_strategy else None
            ),
            "confidence": self.confidence,
            "actual_success": self.actual_success,
            "actual_duration_days": self.actual_duration_days,
        }
