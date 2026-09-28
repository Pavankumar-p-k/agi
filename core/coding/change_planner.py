"""Change planning models for the coding engine (ChangeType, FileChange, ChangePlan)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ChangeType(str, Enum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


@dataclass
class FileChange:
    change_type: ChangeType
    path: str
    description: str = ""


@dataclass
class ChangeStep:
    order: int = 0
    description: str = ""
    file_change: Optional[FileChange] = None


@dataclass
class ChangePlan:
    goal: str = ""
    steps: list[ChangeStep] = field(default_factory=list)
    risk: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {"goal": self.goal, "risk": self.risk,
                "steps": [{"order": s.order, "description": s.description}
                          for s in self.steps]}
