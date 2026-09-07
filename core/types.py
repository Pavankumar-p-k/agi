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
    task_id: str = ""
    user_id: str = "default"
    tenant_id: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


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
