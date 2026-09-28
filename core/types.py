"""Core domain types and data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ExecutionState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id: str = "default"
    goal: str = ""
    state: ExecutionState = ExecutionState.PENDING
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionContext:
    """Context passed to agents when the executor dispatches a sub-goal."""
    task_id: str = ""
    user_id: str = "default"
    tenant_id: str = "default"
    goal: str = ""
    variables: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)


@dataclass
class ExecutionResult:
    status: str = "success"
    output: Any = None
    error: Optional[str] = None


@dataclass
class ModelResult:
    content: str = ""
    model: str = "default"
    usage: dict[str, int] = field(default_factory=dict)
