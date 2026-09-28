"""PlannerResult — strategy ranking artifacts (Rule 51: PlannerStage-only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanningStrategy:
    name: str
    description: str = ""
    confidence: float = 0.0
    estimated_steps: int = 1
    requirements: tuple = ()
    metadata: dict = field(default_factory=dict)


@dataclass
class StrategyComparison:
    left: str = ""
    right: str = ""
    winner: str = ""
    rationale: str = ""
    winner_id: str = ""
    loser_id: str = ""
    margin: float = 0.0


@dataclass
class PlanRanking:
    strategies: tuple = ()
    selected_id: str = ""
    selection_rationale: str = ""
    comparisons: tuple = ()


@dataclass
class PlannerResult:
    plan_id: str = ""
    activity_id: str = ""
    total_candidates: int = 0
    ranking: PlanRanking = field(default_factory=PlanRanking)
    selected_strategy: Any = None
    metadata: dict = field(default_factory=dict)


__all__ = ["PlannerResult", "PlanRanking", "PlanningStrategy",
           "StrategyComparison"]
