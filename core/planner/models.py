from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlannerTemplate:
    template_id: str
    name: str
    description: str
    required_steps: list[str] = field(default_factory=list)
    optional_steps: list[str] = field(default_factory=list)
    success_conditions: list[dict] = field(default_factory=list)
    failure_conditions: list[dict] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    template_id: str
    parameters: dict[str, Any]
    steps: list[dict[str, Any]]
    completed_steps: list[str] = field(default_factory=list)
    pending_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    current_index: int = 0

    @property
    def is_complete(self) -> bool:
        required = [s["name"] for s in self.steps if s.get("required", True)]
        completed_names = {c["name"] for c in self.completed_steps} if self.completed_steps and isinstance(self.completed_steps[0], dict) else set(self.completed_steps)
        return all(r in completed_names for r in required)

    @property
    def missing_steps(self) -> list[str]:
        required = [s["name"] for s in self.steps if s.get("required", True)]
        completed_names = {c["name"] for c in self.completed_steps} if self.completed_steps and isinstance(self.completed_steps[0], dict) else set(self.completed_steps)
        return [r for r in required if r not in completed_names]

    @property
    def halted_early(self) -> bool:
        return self.current_index >= len(self.steps) and not self.is_complete


@dataclass
class SubGoal:
    """A node in the goal decomposition tree.

    Leaf sub-goals map directly to a template or tool step.
    Inner sub-goals decompose into children.
    """
    id: str
    description: str
    template_id: str | None = None          # template if this is a full workflow
    step_name: str | None = None            # step name if this is a single action (no template)
    agent_id: str | None = None             # assigned by AgentRouter during planning
    children: list[SubGoal] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"                 # pending | in_progress | completed | failed
    error: str | None = None

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    @property
    def is_complete(self) -> bool:
        if self.children:
            return all(c.is_complete for c in self.children)
        return self.status == "completed"

    def flatten(self) -> list[SubGoal]:
        """Return depth-first ordered list of leaf sub-goals."""
        if self.is_leaf:
            return [self]
        result = []
        for c in self.children:
            result.extend(c.flatten())
        return result
