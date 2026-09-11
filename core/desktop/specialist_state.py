"""Desktop-owned state for specialist observations and execution history."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import time

from .specialist import DesktopExecutionResult


@dataclass
class DesktopLocalState:
    """Runtime state for one desktop specialist process.

    This is intentionally not a global JARVIS state container.
    """

    active_window: dict[str, Any] | None = None
    applications: list[dict[str, Any]] = field(default_factory=list)
    browser: dict[str, Any] = field(default_factory=dict)
    ui_elements: list[dict[str, Any]] = field(default_factory=list)
    input_state: dict[str, Any] = field(default_factory=dict)
    observations: list[dict[str, Any]] = field(default_factory=list)
    current_task: dict[str, Any] | None = None
    execution_history: list[dict[str, Any]] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def begin_task(self, request_id: str, goal: str) -> None:
        self.current_task = {"request_id": request_id, "goal": goal}
        self.updated_at = time.time()

    def record_result(self, result: DesktopExecutionResult) -> None:
        self.observations.extend(result.observations)
        self.execution_history.append(result.to_dict())
        self.current_task = None
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
