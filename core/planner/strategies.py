"""Module: core.planner.strategies
Strategy abstraction for planner replanning.

A strategy provides enough information to compare alternatives:
    strategy_id
    description
    preconditions
    required_capabilities
    risk
    cost
    expected_success
    fallback_relationship
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, List, Optional


class StrategyStatus(str, Enum):
    """Status of a strategy in the execution lifecycle."""

    AVAILABLE = "available"
    SELECTED = "selected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REPLACED = "replaced"


@dataclass
class Strategy:
    """A reusable execution strategy for a subgoal or phase.

    A strategy describes an alternate execution path that can be
    selected when the primary strategy fails.
    """

    strategy_id: str
    description: str
    preconditions: dict[str, Any] = field(default_factory=dict)
    required_capabilities: List[str] = field(default_factory=list)
    risk: float = 0.5
    cost: float = 0.5
    expected_success: float = 0.5
    fallback_relationship: List[str] = field(default_factory=list)
    status: StrategyStatus = StrategyStatus.AVAILABLE
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_viable(self, available_capabilities: List[str] | None = None) -> bool:
        """Check if the strategy's required capabilities are available."""
        if not self.required_capabilities:
            return True  # no requirements = always viable
        available = set(available_capabilities or [])
        required = set(self.required_capabilities)
        return required.issubset(available)

    def with_updated_status(self, new_status: StrategyStatus) -> "Strategy":
        """Return a new Strategy with updated status."""
        copy = self.__copy__()
        copy.status = new_status
        return copy

    def __copy__(self) -> "Strategy":
        """Shallow copy for status transitions."""
        from copy import copy as _copy
        return _copy(self)


@dataclass
class StrategyRegistry:
    """Registry of available strategies indexed by strategy_id."""

    strategies: dict[str, Strategy] = field(default_factory=dict)

    def register(self, strategy: Strategy) -> None:
        """Register a strategy in the registry."""
        self.strategies[strategy.strategy_id] = strategy

    def get(self, strategy_id: str) -> Strategy | None:
        """Get a strategy by ID."""
        return self.strategies.get(strategy_id)

    def list_strategies(self) -> List[str]:
        """List all registered strategy IDs."""
        return list(self.strategies.keys())

    def get_viable(
        self, available_capabilities: List[str] | None = None,
    ) -> List[Strategy]:
        """Get all strategies whose requirements are met."""
        viable: List[Strategy] = []
        for s in self.strategies.values():
            if s.is_viable(available_capabilities):
                viable.append(s)
        return viable