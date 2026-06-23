from __future__ import annotations

from datetime import datetime
from typing import Any

# Event type constants
WORKFLOW_STARTED = "workflow_started"
WORKFLOW_RESUMED = "workflow_resumed"
STEP_STARTED = "step_started"
STEP_COMPLETED = "step_completed"
STEP_FAILED = "step_failed"
WORKFLOW_COMPLETED = "workflow_completed"
WORKFLOW_FAILED = "workflow_failed"
WORKFLOW_CANCELLED = "workflow_cancelled"
WORKFLOW_RECOVERED = "workflow_recovered"
COMPENSATION_STARTED = "compensation_started"
COMPENSATION_STEP_STARTED = "compensation_step_started"
COMPENSATION_STEP_COMPLETED = "compensation_step_completed"
COMPENSATION_STEP_FAILED = "compensation_step_failed"
WORKFLOW_COMPENSATED = "workflow_compensated"
COMPENSATION_FAILED = "compensation_failed"


class WorkflowEvent:
    def __init__(
        self,
        event_id: str,
        workflow_id: str,
        event_type: str,
        data: dict | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        self.event_id = event_id
        self.workflow_id = workflow_id
        self.event_type = event_type
        self.data = data or {}
        self.timestamp = timestamp or datetime.utcnow()
