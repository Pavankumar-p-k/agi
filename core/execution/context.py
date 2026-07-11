from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ExecutionContext:
    """Shared context for a single execution run across all execution paths.

    This is distinct from ``core.workflow.context.ExecutionContext`` which is
    workflow-scoped. This context spans the entire execution lifecycle from
    the perspective of the calling loop (ControlLoop, AutomationLoop, etc.).
    """
    workflow_id: str
    execution_id: str
    request_id: str = ""
    user_id: str = ""
    source: str = ""
    phase: str = "init"
    status: str = "started"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def advance(self, phase: str, status: str = "in_progress") -> ExecutionContext:
        return ExecutionContext(
            workflow_id=self.workflow_id,
            execution_id=self.execution_id,
            request_id=self.request_id,
            user_id=self.user_id,
            source=self.source,
            phase=phase,
            status=status,
            timestamp=datetime.now(timezone.utc),
            metadata={**self.metadata},
        )

    def to_event_payload(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "source": self.source,
            "phase": self.phase,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
