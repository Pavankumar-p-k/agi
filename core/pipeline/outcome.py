from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Outcome:
    """Structured result of the Execution stage.

    Replaces ad-hoc ``execution_result`` dicts with a typed contract.
    Verification consumes this, Memory stores this, Formatter formats this.
    """

    success: bool
    """Whether execution completed without fatal errors."""

    outputs: dict[str, Any] = field(default_factory=dict)
    """Key-value outputs (at minimum ``{"text": str}``)."""

    artifacts: list[dict[str, Any]] = field(default_factory=list)
    """File/artifact references produced during execution."""

    tool_results: list[dict[str, Any]] = field(default_factory=list)
    """Results of individual tool or plan-step executions."""

    metrics: dict[str, Any] = field(default_factory=dict)
    """Execution-level metrics (token count, duration, provider, …)."""

    activity_id: str | None = None
    """ActivityGraph node id for this execution."""

    errors: list[str] = field(default_factory=list)
    """Non-fatal errors or warnings accumulated during execution."""

    @property
    def text(self) -> str:
        return self.outputs.get("text", "")
