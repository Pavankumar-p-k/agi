"""Planner package: decomposition, templates, state machine, execution."""
from __future__ import annotations

from typing import Any

from core.planner.decomposer import GoalDecomposer
from core.planner.executor import PlannerExecutor
from core.planner.models import ExecutionPlan, PlannerTemplate, SubGoal

__all__ = [
    "GoalDecomposer", "PlannerExecutor", "ExecutionPlan",
    "PlannerTemplate", "SubGoal",
]


def __getattr__(name: str) -> Any:
    # Optional companions imported lazily so the core planner works even if
    # these modules are absent (classifier/state_machine/templates).
    if name == "classifier":
        from core.planner import classifier
        return classifier
    if name in ("PlannerStateMachine", "State"):
        from core.planner.state_machine import PlannerStateMachine, State
        return PlannerStateMachine if name == "PlannerStateMachine" else State
    if name in ("TEMPLATES", "get_template", "list_templates", "match_required_tools"):
        from core.planner import templates
        return getattr(templates, name)
    raise AttributeError(f"module 'core.planner' has no attribute {name!r}")
