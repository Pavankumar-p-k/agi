"""Deprecated — use core.planner.protocol (Plan, PlanStatus) and core.planner.unified_store (UnifiedStore) instead."""

import warnings

from .goal import Goal, GoalStatus
from .goal_manager import GoalManager

__all__ = [
    "Goal",
    "GoalStatus",
    "GoalManager",
]

warnings.warn(
    "brain.goals is deprecated. Use 'core.planner.protocol' for Plan/PlanStatus "
    "and 'core.planner.unified_store' for UnifiedStore instead.",
    DeprecationWarning, stacklevel=2,
)
