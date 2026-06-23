from __future__ import annotations

import enum
from datetime import datetime
from typing import Any


class WorkflowStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RETRYING = "RETRYING"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"


class StepStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkflowStep:
    def __init__(
        self,
        step_id: str,
        idempotency_key: str,
        tool_name: str,
        status: StepStatus = StepStatus.PENDING,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        input_data: dict | None = None,
        output_data: dict | None = None,
        error: str | None = None,
        retry_count: int = 0,
        timeout_seconds: int | None = None,
        max_retries: int = 3,
        compensation_tool: str | None = None,
        compensation_data: dict | None = None,
        compensated: bool = False,
    ) -> None:
        self.step_id = step_id
        self.idempotency_key = idempotency_key
        self.tool_name = tool_name
        self.status = status
        self.started_at = started_at
        self.completed_at = completed_at
        self.input_data = input_data or {}
        self.output_data = output_data or {}
        self.error = error
        self.retry_count = retry_count
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.compensation_tool = compensation_tool
        self.compensation_data = compensation_data or {}
        self.compensated = compensated


_HEARTBEAT_STALE_SECONDS = 60


class WorkflowInstance:
    def __init__(
        self,
        workflow_id: str,
        workflow_type: str,
        status: WorkflowStatus = WorkflowStatus.PENDING,
        current_step: int = 0,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        last_heartbeat: datetime | None = None,
        session_id: str = "",
        owner: str = "",
        timeout_seconds: int | None = None,
        steps: list[WorkflowStep] | None = None,
        artifacts: list[dict] | None = None,
        retry_count: int = 0,
        retry_budget: int = 0,
        parent_workflow_id: str | None = None,
        workflow_version: int = 1,
        execution_context: dict | None = None,
        compensated_steps: list[str] | None = None,
    ) -> None:
        self.workflow_id = workflow_id
        self.workflow_type = workflow_type
        self.status = status
        self.current_step = current_step
        now = datetime.utcnow()
        self.created_at = created_at or now
        self.updated_at = updated_at or now
        self.last_heartbeat = last_heartbeat or now
        self.session_id = session_id
        self.owner = owner
        self.timeout_seconds = timeout_seconds
        self.steps = steps or []
        self.artifacts = artifacts or []
        self.retry_count = retry_count
        self.retry_budget = retry_budget
        self.parent_workflow_id = parent_workflow_id
        self.workflow_version = workflow_version
        self.execution_context = execution_context or {}
        self.compensated_steps = compensated_steps or []

    @property
    def is_stale(self) -> bool:
        if self.status not in (WorkflowStatus.RUNNING, WorkflowStatus.COMPENSATING):
            return False
        if self.last_heartbeat is None:
            return True
        elapsed = (datetime.utcnow() - self.last_heartbeat).total_seconds()
        return elapsed > _HEARTBEAT_STALE_SECONDS


class StepDefinition:
    def __init__(
        self,
        tool_name: str,
        input_data: dict | None = None,
        timeout_seconds: int | None = None,
        max_retries: int = 3,
        compensation_tool: str | None = None,
        compensation_data: dict | None = None,
        retry_budget: int = 0,
    ) -> None:
        self.tool_name = tool_name
        self.input_data = input_data or {}
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.compensation_tool = compensation_tool
        self.compensation_data = compensation_data or {}
        self.retry_budget = retry_budget
