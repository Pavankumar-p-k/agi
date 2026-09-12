"""Module: core.planner.comparison
Strategy comparison using explicit, deterministic criteria.

At minimum consider:
    • capability availability
    • prerequisites
    • previous failure information
    • reliability / success history (if available)
    • cost / complexity
    • risk
    • verification availability

If the repository does not currently contain enough information for a
criterion, it is treated as unavailable / neutral.

The comparison must produce an explainable selection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


class ComparisonCriterion(str, Enum):
    """Explicit criteria used in strategy comparison."""

    CAPABILITY_AVAILABILITY = "capability_availability"
    PREREQUISITES = "prerequisites"
    FAILURE_HISTORY = "failure_history"
    RELIABILITY = "reliability"
    COST = "cost"
    RISK = "risk"
    VERIFICATION = "verification"


@dataclass
class StrategyProfile:
    """Profile of a strategy used by the comparison engine."""

    strategy_id: str
    description: str
    preconditions: dict[str, Any] = field(default_factory=dict)
    required_capabilities: List[str] = field(default_factory=list)
    risk: float = 0.5  # 0.0 = no risk, 1.0 = maximum risk
    cost: float = 0.5  # 0.0 = no cost, 1.0 = maximum cost
    expected_success: float = 0.5  # 0.0 = guaranteed failure, 1.0 = guaranteed success
    verification_available: bool = False
    fallback_relationship: List[str] = field(default_factory=list)  # strategy IDs this can fallback to
    previous_failure_count: int = 0
    success_history: float = 0.5  # 0.0 = never succeeded, 1.0 = always succeeded


@dataclass
class ComparisonResult:
    """Result of comparing available strategies."""

    ranked_strategies: List[Tuple[str, float]]  # (strategy_id, score), highest first
    selected_strategy_id: str | None = None
    explanation: str = ""
    criteria_used: Dict[ComparisonCriterion, Any] = field(default_factory=dict)
    neutral_criteria: List[ComparisonCriterion] = field(default_factory=list)
    # Per-strategy scores per criterion
    strategy_scores: Dict[str, Dict[ComparisonCriterion, float]] = field(
        default_factory=dict
    )


class StrategyComparator:
    """Compare strategy profiles using explicit, deterministic criteria."""

    def __init__(self, profiles: List[StrategyProfile] | None = None):
        self.profiles: Dict[str, StrategyProfile] = {
            p.strategy_id: p for p in profiles or []
        }

    def compare(
        self, criteria: Dict[ComparisonCriterion, Any] | None = None,
    ) -> ComparisonResult:
        """Compare all known strategies and return a ranked result.

        Criteria are optional; missing criteria are treated as neutral.
        """
        criteria = criteria or {}
        ranked: List[Tuple[str, float]] = []
        strategy_scores: Dict[str, Dict[ComparisonCriterion, float]] = {}

        for strategy_id, profile in self.profiles.items():
            scores: Dict[ComparisonCriterion, float] = {}
            total = 0.0
            count = 0

            for criterion in ComparisonCriterion:
                if criterion in criteria:
                    value = criteria[criterion]
                    # Apply criterion-specific scoring
                    score = self._score_criterion(criterion, value, profile)
                    scores[criterion] = score
                    total += score
                    count += 1
                else:
                    # Neutral — treat as midpoint (0.5) for averaging
                    scores[criterion] = 0.5
                    total += 0.5
                    count += 1

            average = total / count if count > 0 else 0.5
            ranked.append((strategy_id, average))
            strategy_scores[strategy_id] = scores

        # Rank by score descending
        ranked.sort(key=lambda x: x[1], reverse=True)

        # Build explanation
        explanation_parts: List[str] = []
        for strategy_id, score in ranked:
            profile = self.profiles[strategy_id]
            parts = [f"{strategy_id}: score={score:.2f}"]
            if profile.required_capabilities:
                parts.append(f"capabilities={profile.required_capabilities}")
            if profile.risk != 0.5:
                parts.append(f"risk={profile.risk:.2f}")
            if profile.cost != 0.5:
                parts.append(f"cost={profile.cost:.2f}")
            if profile.expected_success != 0.5:
                parts.append(f"success={profile.expected_success:.2f}")
            explanation_parts.append(" ".join(parts))

        explanation = " | ".join(explanation_parts)

        # Determine selection
        selected_strategy_id = ranked[0][0] if ranked else None

        # Separate neutral criteria (those where all strategies scored 0.5)
        neutral_criteria: List[ComparisonCriterion] = []
        for criterion in ComparisonCriterion:
            scores = [strategy_scores[sid].get(criterion, 0.5) for sid in self.profiles]
            if all(s == 0.5 for s in scores):
                neutral_criteria.append(criterion)

        return ComparisonResult(
            ranked_strategies=ranked,
            selected_strategy_id=selected_strategy_id,
            explanation=explanation,
            criteria_used={k: v for k, v in criteria.items() if k in ComparisonCriterion},
            neutral_criteria=neutral_criteria,
            strategy_scores=strategy_scores,
        )

    def _score_criterion(
        self, criterion: ComparisonCriterion, value: Any, profile: StrategyProfile,
    ) -> float:
        """Score a single strategy against a single criterion.

        Returns a float in [0.0, 1.0]. Missing/invalid values are treated
        as neutral (0.5).
        """
        if criterion == ComparisonCriterion.CAPABILITY_AVAILABILITY:
            available = set(profile.required_capabilities) if profile.required_capabilities else set()
            if not available:
                return 1.0  # no requirements = fully available
            # Partial availability: count how many are "satisfied"
            # In the absence of a capability registry, treat as neutral
            return 0.5

        if criterion == ComparisonCriterion.PREREQUISITES:
            # Fewer/weaker prerequisites = better
            deps = len(profile.preconditions) if profile.preconditions else 0
            return max(0.0, 1.0 - deps * 0.1)

        if criterion == ComparisonCriterion.FAILURE_HISTORY:
            # Lower failure count = better
            fc = profile.previous_failure_count
            return max(0.0, 1.0 - fc * 0.15)

        if criterion == ComparisonCriterion.RELIABILITY:
            # Use expected_success or history
            return profile.expected_success

        if criterion == ComparisonCriterion.COST:
            # Lower cost = better
            return max(0.0, 1.0 - profile.cost)

        if criterion == ComparisonCriterion.RISK:
            # Lower risk = better
            return max(0.0, 1.0 - profile.risk)

        if criterion == ComparisonCriterion.VERIFICATION:
            return 1.0 if profile.verification_available else 0.5

        # Default neutral
        return 0.5