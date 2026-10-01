"""Strategic reasoning v2 models (Phase 15.1-15.2)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List


class _StrEnum(str, Enum):
    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value == value:
                    return member
        return None


class TimeHorizon(_StrEnum):
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


class StrategyStatus(_StrEnum):
    CANDIDATE = "candidate"
    SELECTED = "selected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"


class ImpactDimension(_StrEnum):
    CODING = "coding"
    BROWSER = "browser"
    MEMORY = "memory"
    RESEARCH = "research"
    GENERAL = "general"
    PERFORMANCE = "performance"


def _enum_value(value):
    return getattr(value, "value", value)


@dataclass
class StrategyCandidate:
    strategy_id: str
    name: str = ""
    description: str = ""
    proposal_ids: List[str] = field(default_factory=list)
    impact_by_dimension: Dict[str, float] = field(default_factory=dict)
    overall_improvement: float = 0.0
    risk: float = 0.0
    implementation_cost: float = 0.0
    confidence: float = 0.0
    time_horizon: TimeHorizon = TimeHorizon.MEDIUM_TERM
    status: StrategyStatus = StrategyStatus.CANDIDATE
    enabled_strategy_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "proposal_ids": list(self.proposal_ids),
            "impact_by_dimension": dict(self.impact_by_dimension),
            "overall_improvement": self.overall_improvement,
            "risk": self.risk,
            "implementation_cost": self.implementation_cost,
            "confidence": self.confidence,
            "time_horizon": _enum_value(self.time_horizon),
            "status": _enum_value(self.status),
            "enabled_strategy_ids": list(self.enabled_strategy_ids),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyCandidate":
        return cls(
            strategy_id=data.get("strategy_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            proposal_ids=list(data.get("proposal_ids", []) or []),
            impact_by_dimension=dict(data.get("impact_by_dimension", {}) or {}),
            overall_improvement=float(data.get("overall_improvement", 0.0)),
            risk=float(data.get("risk", 0.0)),
            implementation_cost=float(data.get("implementation_cost", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            time_horizon=TimeHorizon(data.get("time_horizon", "medium_term")),
            status=StrategyStatus(data.get("status", "candidate")),
            enabled_strategy_ids=list(data.get("enabled_strategy_ids", []) or []),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class TradeoffAnalysis:
    strategy_id: str
    net_utility: float = 0.0
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    option_value: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StrategicDecision:
    decision_id: str
    chosen_strategy_id: str
    alternative_strategy_ids: List[str] = field(default_factory=list)
    rationale: str = ""
    utility_scores: Dict[str, float] = field(default_factory=dict)
    status: StrategyStatus = StrategyStatus.SELECTED
    tradeoff_analyses: List[TradeoffAnalysis] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "chosen_strategy_id": self.chosen_strategy_id,
            "alternative_strategy_ids": list(self.alternative_strategy_ids),
            "rationale": self.rationale,
            "utility_scores": dict(self.utility_scores),
            "status": _enum_value(self.status),
            "tradeoff_analyses": [a.to_dict() for a in self.tradeoff_analyses],
        }


@dataclass
class ResourceBudget:
    effort_budget: float = 40.0
    max_concurrent: int = 1
    min_utility_threshold: float = 0.0


@dataclass
class PortfolioAllocation:
    selected: List[StrategyCandidate] = field(default_factory=list)
    selected_analyses: List[TradeoffAnalysis] = field(default_factory=list)
    deferred: List[StrategyCandidate] = field(default_factory=list)
    deferred_analyses: List[TradeoffAnalysis] = field(default_factory=list)
    total_effort_consumed: float = 0.0
    total_expected_value: float = 0.0
    remaining_effort: float = 40.0
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected": [c.to_dict() for c in self.selected],
            "selected_analyses": [a.to_dict() for a in self.selected_analyses],
            "deferred": [c.to_dict() for c in self.deferred],
            "deferred_analyses": [a.to_dict() for a in self.deferred_analyses],
            "total_effort_consumed": self.total_effort_consumed,
            "total_expected_value": self.total_expected_value,
            "remaining_effort": self.remaining_effort,
            "rationale": self.rationale,
        }
