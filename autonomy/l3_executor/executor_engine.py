from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jarvis_os.runtime.exceptions import RuntimeBoundaryViolation


@dataclass
class ExecutorResult:
    status: str
    output: str
    steps_done: int
    steps_total: int


class ExecutorEngine:
    """
    Minimal real executor: validates input, applies callable steps, and returns concrete state.
    """

    def execute(self, goal: str, steps: list[dict[str, Any]] | None = None) -> ExecutorResult:
        if not goal.strip():
            raise RuntimeBoundaryViolation("ExecutorEngine rejected empty goal.")
        pipeline = list(steps or [])
        output_chunks: list[str] = []
        completed = 0
        for step in pipeline:
            action = step.get("action")
            if callable(action):
                output_chunks.append(str(action(step.get("args", {}))))
            else:
                output_chunks.append(str(step.get("description", "step-complete")))
            completed += 1
        return ExecutorResult(
            status="success",
            output="\n".join(output_chunks).strip(),
            steps_done=completed,
            steps_total=len(pipeline),
        )
