# core/execution/__init__.py
# Shared execution infrastructure for all execution paths.

from core.execution.context import ExecutionContext
from core.execution.manager import ExecutionManager

__all__ = [
    "ExecutionContext",
    "ExecutionManager",
]
