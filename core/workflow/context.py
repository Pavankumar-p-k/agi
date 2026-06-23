from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ExecutionContext:
    workflow_id: str
    owner: str
    session_id: str
    variables: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ContextManager:
    def __init__(self, store: "WorkflowStore") -> None:
        self._store = store

    def create_context(
        self,
        workflow_id: str,
        owner: str = "",
        session_id: str = "",
        variables: dict | None = None,
        artifacts: dict | None = None,
        metadata: dict | None = None,
    ) -> ExecutionContext:
        now = datetime.utcnow()
        ctx = ExecutionContext(
            workflow_id=workflow_id,
            owner=owner,
            session_id=session_id,
            variables=variables or {},
            artifacts=artifacts or {},
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self._store.create_context(ctx)
        return ctx

    def get_context(self, workflow_id: str) -> ExecutionContext | None:
        return self._store.get_context(workflow_id)

    def update_context(self, ctx: ExecutionContext) -> None:
        ctx.updated_at = datetime.utcnow()
        self._store.update_context(ctx)

    def delete_context(self, workflow_id: str) -> None:
        self._store.delete_context(workflow_id)
