from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ExecutionContext:
    workflow_id: str = ""
    execution_id: str = ""
    source: str = ""
    user_id: str | None = None
    phase: str = "init"
    status: str = "started"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def advance(self, phase: str, status: str) -> "ExecutionContext":
        return replace(self, phase=phase, status=status)

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id, "execution_id": self.execution_id,
            "source": self.source, "user_id": self.user_id, "phase": self.phase,
            "status": self.status, "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": dict(self.metadata),
        }
