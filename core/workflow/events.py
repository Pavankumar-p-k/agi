"""Workflow event records and event-type constants."""

from __future__ import annotations

from dataclasses import dataclass, field

WORKFLOW_STARTED = "workflow_started"
STEP_STARTED = "step_started"
STEP_COMPLETED = "step_completed"
WORKFLOW_COMPLETED = "workflow_completed"
WORKFLOW_FAILED = "workflow_failed"
WORKFLOW_CANCELLED = "workflow_cancelled"
IDEMPOTENCY_HIT = "idempotency_hit"


@dataclass
class MJEvent:
    """A persisted workflow event."""

    event_type: str = ""
    workflow_id: str = ""
    data: dict = field(default_factory=dict)
    timestamp: float = 0.0
