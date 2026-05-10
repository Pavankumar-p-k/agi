from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .executor_engine import ExecutorEngine

# Alias for backward compatibility
ExecutionResult = "LayerExecutionResult"


class ExecStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class LayerExecutionResult:
    status: ExecStatus
    output: str
    steps_done: int
    steps_total: int
    error: str = ""


# Alias for backward compatibility
ExecutionResult = LayerExecutionResult


class ExecutorLayer:
    def __init__(self, engine: ExecutorEngine | None = None) -> None:
        self._engine = engine or ExecutorEngine()

    async def execute(self, goal: str, intent: str = "task", context: str = "", dry_run: bool = False) -> LayerExecutionResult:
        del intent, context
        if dry_run:
            return LayerExecutionResult(status=ExecStatus.SUCCESS, output="dry-run plan prepared", steps_done=0, steps_total=0)
        result = self._engine.execute(goal, steps=[{"description": goal}])
        return LayerExecutionResult(
            status=ExecStatus.SUCCESS if result.status == "success" else ExecStatus.FAILED,
            output=result.output,
            steps_done=result.steps_done,
            steps_total=result.steps_total,
        )
