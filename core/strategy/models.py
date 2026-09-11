"""Minimal strategy data contracts used by coding benchmarks."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Prediction:
    success_probability: float = 0.5
    estimated_duration_days: float = 7.0
    estimated_risk: float = 0.5
    estimated_effort: float = 5.0
    confidence: float = 0.3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceBundle:
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Strategy:
    name: str
    description: str = ""
    goal: str = ""
    prediction: Prediction = field(default_factory=Prediction)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["prediction"] = self.prediction.to_dict()
        return data


@dataclass
class StrategyDecision:
    decision_id: str
    goal: str
    timestamp: datetime
    strategies_considered: list[Strategy] = field(default_factory=list)
    chosen_strategy: Strategy | None = None
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "goal": self.goal,
            "timestamp": self.timestamp.isoformat(),
            "strategies_considered": [strategy.to_dict() for strategy in self.strategies_considered],
            "chosen_strategy": self.chosen_strategy.to_dict() if self.chosen_strategy else None,
            "confidence": self.confidence,
        }


@dataclass
class StrategyTag:
    name: str
    weight: float = 1.0
