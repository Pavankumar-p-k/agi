"""Planner protocol definitions."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PlanStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Plan:
    id: str = "default"
    goal: str = ""
    status: PlanStatus = PlanStatus.PENDING
    steps: list[Any] = field(default_factory=list)


class Planner:
    def create_plan(self, goal: str, **kwargs) -> Plan:
        return Plan(goal=goal)
