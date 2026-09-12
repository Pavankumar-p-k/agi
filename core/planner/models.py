"""Module: core.planner.models
Data models for planner sub-goals, execution plans, and templates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, List, Optional


class PlanStatus(str, Enum):
    """Status of a planning cycle."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REPLANNED = "replanned"
    ABORTED = "aborted"


@dataclass
class SubGoal:
    """A sub-goal within a plan, with goal description and tracking info.

    SubGoal is the basic executable unit that the planner decomposes
    a high-level goal into, and that the executor executes step by step.
    """
    id: str = ""
    goal: str = ""
    status: PlanStatus = PlanStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    agent_id: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return self.completed_at - self.started_at

    def mark_running(self) -> None:
        self.status = PlanStatus.IN_PROGRESS
        self.started_at = self.started_at or __import__("time").time()

    def mark_completed(self, artifacts: dict[str, Any] | None = None) -> None:
        self.status = PlanStatus.COMPLETED
        self.completed_at = __import__("time").time()
        if artifacts:
            self.artifacts.update(artifacts)

    def mark_failed(self, error: str) -> None:
        self.status = PlanStatus.FAILED
        self.started_at = None
        self.completed_at = __import__("time").time()


@dataclass
class ExecutionPlan:
    """A complete execution plan composed of sub-goals.

    An ExecutionPlan owns its sub-goals and tracks the overall plan
    status, making it distinguishable from other plans (e.g. revised plans
    have different hashes).
    """
    id: str = ""
    goal: str = ""
    status: PlanStatus = PlanStatus.PENDING
    sub_goals: list[SubGoal] = field(default_factory=list)
    created_at: float | None = None
    revised_from: str | None = None  # plan ID this was revised from

    @property
    def plan_hash(self) -> str:
        """Deterministic hash identifying this plan version."""
        description = f"{self.id}:{self.goal}:{[sg.id for sg in self.sub_goals]}"
        return __import__("hashlib").sha256(description.encode()).hexdigest()[:16]

    def add_sub_goal(self, sg: SubGoal) -> None:
        self.sub_goals.append(sg)

    def get_sub_goal(self, sg_id: str) -> SubGoal | None:
        for sg in self.sub_goals:
            if sg.id == sg_id:
                return sg
        return None


@dataclass
class PlanTemplate:
    """A template for plan decomposition, describing what sub-goals
    a typical decomposition of a goal class should produce.

    Templates are used by the decomposer to generate consistent
    sub-goal structures for similar goal types.
    """
    name: str = ""
    description: str = ""
    typical_sub_goals: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)


def __getattr__(name: str) -> Any:
    """Fallback for any undefined names (compat layer)."""
    import types
    return types.ModuleType(name)