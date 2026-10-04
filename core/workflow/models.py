"""Workflow runtime models: statuses, step definitions, workflow instance."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class WorkflowStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY = "RETRY"
    SKIPPED = "SKIPPED"


@dataclass
class StepDefinition:
    """Declarative definition of one workflow step."""

    tool_name: str = ""
    input_data: dict = field(default_factory=dict)
    compensation_tool: str | None = None
    compensation_data: dict | None = None
    max_retries: int = 2
    timeout_seconds: float | None = None
    idempotency_key: str | None = None

    @property
    def tool_type(self) -> str:
        return self.tool_name

    @property
    def content(self):
        if (
            isinstance(self.input_data, dict)
            and "command" in self.input_data
            and len(self.input_data) == 1
        ):
            return self.input_data["command"]
        import json

        return json.dumps(self.input_data)


@dataclass
class WorkflowStep:
    """A concrete step instance within a workflow run."""

    step_id: str = field(default_factory=lambda: f"step_{uuid.uuid4().hex[:12]}")
    idempotency_key: str = ""
    tool_name: str = ""
    status: StepStatus = StepStatus.PENDING
    error: str | None = None
    retry_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_data: dict = field(default_factory=dict)
    output: dict | None = None
    compensation_tool: str | None = None
    compensation_data: dict | None = None
    max_retries: int = 2
    timeout_seconds: float | None = None
    compensated: bool = False

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "idempotency_key": self.idempotency_key,
            "tool_name": self.tool_name,
            "status": self.status.value
            if isinstance(self.status, StepStatus)
            else str(self.status),
            "error": self.error,
            "retry_count": self.retry_count,
            "started_at": self.started_at.isoformat()
            if self.started_at is not None
            else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at is not None
            else None,
            "input_data": self.input_data,
            "output": self.output,
            "compensation_tool": self.compensation_tool,
            "compensation_data": self.compensation_data,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "compensated": self.compensated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowStep":
        started = data.get("started_at")
        completed = data.get("completed_at")
        status = data.get("status", StepStatus.PENDING.value)
        return cls(
            step_id=data.get("step_id") or f"step_{uuid.uuid4().hex[:12]}",
            idempotency_key=data.get("idempotency_key", ""),
            tool_name=data.get("tool_name", ""),
            status=StepStatus(status),
            error=data.get("error"),
            retry_count=int(data.get("retry_count", 0) or 0),
            started_at=datetime.fromisoformat(started) if started else None,
            completed_at=datetime.fromisoformat(completed) if completed else None,
            input_data=data.get("input_data") or {},
            output=data.get("output"),
            compensation_tool=data.get("compensation_tool"),
            compensation_data=data.get("compensation_data"),
            max_retries=int(data.get("max_retries", 2)),
            timeout_seconds=data.get("timeout_seconds"),
            compensated=bool(data.get("compensated", False)),
        )


# Threshold beyond which a running workflow's heartbeat counts as stale.
STALE_HEARTBEAT_SECONDS = 60.0


@dataclass
class WorkflowInstance:
    """A workflow run and all of its execution state."""

    workflow_id: str = field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:12]}")
    workflow_type: str = ""
    status: WorkflowStatus = WorkflowStatus.PENDING
    steps: list[WorkflowStep] = field(default_factory=list)
    execution_context: dict = field(default_factory=dict)
    artifacts: list = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: datetime | None = None
    current_step: int = 0
    owner: str | None = None
    session_id: str | None = None
    retry_budget: int = 0
    retry_count: int = 0
    compensated_steps: list[str] = field(default_factory=list)

    @property
    def is_stale(self) -> bool:
        if self.last_heartbeat is None:
            return False
        age = (datetime.utcnow() - self.last_heartbeat).total_seconds()
        return age > STALE_HEARTBEAT_SECONDS
