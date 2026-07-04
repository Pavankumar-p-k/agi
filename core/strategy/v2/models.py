"""Phase 15.1 — Strategic Reasoning models.

Data model for comparing improvement proposals across multiple
dimensions and selecting the best strategic next step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TimeHorizon(str, Enum):
    SHORT_TERM = "short_term"     # days
    MEDIUM_TERM = "medium_term"   # weeks
    LONG_TERM = "long_term"       # months+


class StrategyStatus(str, Enum):
    CANDIDATE = "candidate"
    SELECTED = "selected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"


class ImpactDimension(str, Enum):
    CODING = "coding"
    RESEARCH = "research"
    MEMORY = "memory"
    PLANNING = "planning"
    BROWSER = "browser"
    BUILD = "build"
    COLLABORATION = "collaboration"
    STRATEGY = "strategy"
    GENERAL = "general"


# ── Phase 15.2 — Resource models ──────────────────────────────────


@dataclass
class ResourceBudget:
    """Available resources for executing strategies.

    The budget constrains which strategies can be pursued.
    Strategies are selected to maximize utility within these limits.

    Usage:
        budget = ResourceBudget(effort_budget=40.0)
        optimizer = PortfolioOptimizer()
        allocation = optimizer.optimize(candidates, analyses, budget)
    """

    effort_budget: float = 40.0       # in abstract effort units
    max_concurrent: int = 1            # strategies runnable in parallel
    min_utility_threshold: float = 0.0  # reject strategies below this

    def to_dict(self) -> dict[str, Any]:
        return {
            "effort_budget": self.effort_budget,
            "max_concurrent": self.max_concurrent,
            "min_utility_threshold": self.min_utility_threshold,
        }


@dataclass
class PortfolioAllocation:
    """Result of resource-constrained strategy selection.

    Splits strategies into two groups:
      - Selected: strategies to execute now (within budget)
      - Deferred: strategies queued for future execution
    """

    selected: list[StrategyCandidate]
    selected_analyses: list[TradeoffAnalysis]
    deferred: list[StrategyCandidate]
    deferred_analyses: list[TradeoffAnalysis]

    total_effort_consumed: float
    total_expected_value: float
    remaining_effort: float
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": [c.to_dict() for c in self.selected],
            "deferred": [c.to_dict() for c in self.deferred],
            "total_effort_consumed": round(self.total_effort_consumed, 3),
            "total_expected_value": round(self.total_expected_value, 3),
            "remaining_effort": round(self.remaining_effort, 3),
            "rationale": self.rationale,
        }


# ── Core models ──────────────────────────────────────────────────


@dataclass
class StrategyCandidate:
    """A possible strategic direction — a bundle of one or more proposals."""

    strategy_id: str
    name: str
    description: str
    proposal_ids: list[str]          # constituent proposal IDs

    # Multi-dimensional impact assessment
    impact_by_dimension: dict[str, float]  # dimension → expected gain (0.0–1.0)
    overall_improvement: float       # aggregate expected improvement (0.0–1.0)
    risk: float                      # 0.0 (safe) → 1.0 (very risky)
    implementation_cost: float       # 0.0 (trivial) → 1.0 (very expensive)
    confidence: float                # 0.0–1.0 how certain is the prediction

    time_horizon: TimeHorizon = TimeHorizon.MEDIUM_TERM
    status: StrategyStatus = StrategyStatus.CANDIDATE
    enabled_strategy_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "proposal_ids": list(self.proposal_ids),
            "impact_by_dimension": dict(self.impact_by_dimension),
            "overall_improvement": round(self.overall_improvement, 3),
            "risk": round(self.risk, 3),
            "implementation_cost": round(self.implementation_cost, 3),
            "confidence": round(self.confidence, 3),
            "time_horizon": self.time_horizon.value,
            "status": self.status.value,
            "enabled_strategy_ids": list(self.enabled_strategy_ids),
        }


@dataclass
class TradeoffAnalysis:
    """Comparison of a strategy across decision dimensions.

    Includes option_value: the estimated future value of strategies
    this candidate unlocks. A strategy that enables future improvements
    scores higher than one that doesn't, even if their direct utilities
    are similar.
    """

    strategy_id: str
    net_utility: float               # final weighted score
    dimension_scores: dict[str, float]  # per-dimension utility contribution
    strengths: list[str]             # dimensions where this excels
    weaknesses: list[str]            # dimensions where this is weak
    option_value: float = 0.0        # future option value (utility of enabled strategies)
    tradeoff_notes: str = ""         # human-readable comparison summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "net_utility": round(self.net_utility, 3),
            "dimension_scores": {k: round(v, 3) for k, v in self.dimension_scores.items()},
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
            "option_value": round(self.option_value, 3),
            "tradeoff_notes": self.tradeoff_notes,
        }


@dataclass
class StrategicDecision:
    """The output of the strategic reasoning layer.

    Records what was chosen, why, and what was rejected.
    """

    decision_id: str
    chosen_strategy_id: str
    alternative_strategy_ids: list[str]
    rationale: str
    utility_scores: dict[str, float]   # strategy_id → utility
    tradeoff_analyses: list[TradeoffAnalysis] = field(default_factory=list)

    status: StrategyStatus = StrategyStatus.SELECTED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "chosen_strategy_id": self.chosen_strategy_id,
            "alternative_strategy_ids": list(self.alternative_strategy_ids),
            "rationale": self.rationale,
            "utility_scores": {k: round(v, 3) for k, v in self.utility_scores.items()},
            "status": self.status.value,
        }
