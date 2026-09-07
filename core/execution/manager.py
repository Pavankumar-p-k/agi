from __future__ import annotations

import uuid
from .context import ExecutionContext


class ExecutionManager:
    @staticmethod
    def create_context(source: str = "", user_id: str | None = None, **kwargs) -> ExecutionContext:
        return ExecutionContext(execution_id=str(uuid.uuid4()), source=source, user_id=user_id, **kwargs)
