"""Planner models: SubGoal tree, ExecutionPlan, PlannerTemplate, PlanStep."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SubGoal:
    """A node in the goal decomposition tree.

    Leaves (no children) are the executable units the agent system runs.
    """
    id: str = ""
    description: str = ""
    step_name: str = ""
    template_id: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    children: list["SubGoal"] = field(default_factory=list)
    status: str = "pending"
    result: Optional[Any] = None

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def flatten(self) -> list["SubGoal"]:
        """All leaf nodes, depth-first."""
        leaves: list[SubGoal] = []
        if self.is_leaf:
            return [self]
        for child in self.children:
            leaves.extend(child.flatten())
        return leaves

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class PlanStep:
    name: str = ""
    description: str = ""
    agent_id: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """A plan: ordered steps derived from a goal."""
    id: str = "plan"
    goal: str = ""
    template_id: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    subgoals: list[SubGoal] = field(default_factory=list)
    status: str = "pending"

    def add_step(self, step: PlanStep) -> None:
        self.steps.append(step)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "goal": self.goal, "template_id": self.template_id,
            "status": self.status,
            "steps": [{"name": s.name, "agent_id": s.agent_id} for s in self.steps],
        }


@dataclass
class PlannerTemplate:
    """Named plan template: required steps + optional tool hints."""
    id: str = ""
    name: str = ""
    steps: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "steps": list(self.steps),
                "required_tools": list(self.required_tools)}
