from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.pipeline.context import PipelineContext


class StageOutcome(Enum):
    """Result of executing a single pipeline stage."""

    CONTINUE = "continue"
    """Stage succeeded; proceed to the next stage in sequence."""

    SHORT_CIRCUIT = "short_circuit"
    """Stage decided processing is complete (e.g. auth denied);
    skip remaining stages and go directly to response formatting."""

    RETRY = "retry"
    """Stage failed transiently; caller may retry (up to a configured limit)."""

    FAIL = "fail"
    """Stage failed permanently; pipeline halts with an error response."""

    DEFER = "defer"
    """Stage cannot complete yet (e.g. waiting for user input);
    pipeline is suspended and can be resumed later."""


@dataclass
class StageResult:
    """Outcome of executing a single pipeline stage."""

    outcome: StageOutcome
    """How the stage completed."""

    context: PipelineContext
    """Snapshot of the pipeline context after this stage ran."""

    error: str | None = None
    """Human-readable error message (only meaningful for FAIL / RETRY)."""

    retry_count: int = 0
    """Number of times this stage has been retried so far."""

    metrics: dict[str, Any] = field(default_factory=dict)
    """Arbitrary metrics emitted by this stage (duration, token count, …)."""


class PipelineStage(ABC):
    """A single stage in the canonical request processing pipeline.

    Every stage receives the full ``PipelineContext``, reads what it needs,
    writes what it produces, and returns a ``StageResult`` indicating whether
    the pipeline should continue, short-circuit, retry, or fail.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this stage (e.g. ``"intent"``, ``"execution"``)."""
        ...

    @abstractmethod
    async def execute(self, context: PipelineContext) -> StageResult:
        """Execute this stage.

        Args:
            context: The mutable pipeline context for the current request.

        Returns:
            A ``StageResult`` describing the outcome.
        """
        ...
