"""Execution context for brain/workflow orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrainExecutionContext:
    task_id: str = ""
    workflow_id: str = ""
    execution_id: str = ""
    status: str = "pending"
    source: str = "api"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "status": self.status,
            "source": self.source,
            "metadata": dict(self.metadata),
        }

    def copy(self) -> "BrainExecutionContext":
        return BrainExecutionContext(
            task_id=self.task_id,
            workflow_id=self.workflow_id,
            execution_id=self.execution_id,
            status=self.status,
            source=self.source,
            metadata=dict(self.metadata),
        )
