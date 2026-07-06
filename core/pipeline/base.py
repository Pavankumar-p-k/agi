from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from core.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)

# ── Stage ownership ───────────────────────────────────────────────────────────
# Maps each stage name to the set of PipelineContext fields it owns.
# Non-owner stages writing to these fields will trigger a runtime warning.
STAGE_OWNERSHIP: dict[str, set[str]] = {
    "receive": {"parsed_request"},
    "load_context": {"metadata", "session_id", "user_id"},
    "authentication": set(),
    "rate_limit": set(),
    "intent": {"classification"},
    "context_retrieval": {"retrieved_context"},
    "reasoner": {"reasoning_assessment"},
    "planner": {"plan"},
    "plan_validator": {"plan_validated"},
    "capability_selection": {"selected_capabilities"},
    "execution": {"execution_result", "execution_state", "outcome"},
    "verification": {"verification_result"},
    "epistemic": {"epistemic_tags"},
    "memory": {"memory_refs", "store_decision"},
    "metrics": {"metrics"},
    "formatter": {"formatted_response"},
}
"""Stage name → set of context fields that stage exclusively owns.

Every other stage may *read* these fields but must not *write* them.
Ownership is enforced at runtime by ``PipelineContext.set_stage_field()``."""


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

    CANCELLED = "cancelled"
    """Pipeline execution was cancelled externally (e.g. WebSocket disconnect,
    voice interruption, scheduler stop).  The request is abandoned."""


@dataclass
class StageResult:
    """Outcome of executing a single pipeline stage."""

    outcome: StageOutcome
    """How the stage completed."""

    context: PipelineContext
    """Snapshot of the pipeline context after this stage ran."""

    error: str | None = None
    """Human-readable error message (only meaningful for FAIL / RETRY / CANCELLED)."""

    retry_count: int = 0
    """Number of times this stage has been retried so far."""

    metrics: dict[str, Any] = field(default_factory=dict)
    """Arbitrary metrics emitted by this stage (duration, token count, …)."""


class PipelineStage(ABC):
    """A single stage in the canonical request processing pipeline.

    Every stage receives the full ``PipelineContext``, reads what it needs,
    writes what it produces, and returns a ``StageResult`` indicating whether
    the pipeline should continue, short-circuit, retry, or fail.

    Subclasses may override ``max_retries`` and ``timeout`` to tune
    resilience for their specific behaviour.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this stage (e.g. ``"intent"``, ``"execution"``)."""
        ...

    max_retries: int = 3
    """Maximum number of automatic retries when the stage returns RETRY."""

    timeout: float | None = None
    """Optional timeout in seconds for this stage's ``execute()`` call."""

    owned_fields: set[str] = set()
    """Context fields this stage owns (see ``STAGE_OWNERSHIP``)."""

    @abstractmethod
    async def execute(self, context: PipelineContext) -> StageResult:
        """Execute this stage.

        Args:
            context: The mutable pipeline context for the current request.

        Returns:
            A ``StageResult`` describing the outcome.
        """
        ...


# ── Lifecycle hook types ─────────────────────────────────────────────────────

HookCallback = Callable[[str, PipelineContext], None]
"""Callback signature for pipeline lifecycle hooks.

Args:
    stage_name: The stage being entered / exited.
    context: The current pipeline context.
"""


class HookRegistry:
    """Registry of lifecycle hooks for the pipeline.

    Hooks are called **before** and **after** each stage's ``execute()``
    method.  They receive the stage name and the current context for
    observability, metrics, and plugin integration.

    Plugin code should **not** modify the context directly — use a stage
    instead.
    """

    def __init__(self) -> None:
        self._before: dict[str, list[HookCallback]] = {}
        self._after: dict[str, list[HookCallback]] = {}

    def on_before(self, stage_name: str, callback: HookCallback) -> None:
        """Register a callback to run **before** *stage_name* executes."""
        self._before.setdefault(stage_name, []).append(callback)

    def on_after(self, stage_name: str, callback: HookCallback) -> None:
        """Register a callback to run **after** *stage_name* executes."""
        self._after.setdefault(stage_name, []).append(callback)

    async def fire_before(self, stage_name: str, context: PipelineContext) -> None:
        for cb in self._before.get(stage_name, []):
            try:
                cb(stage_name, context)
            except Exception:
                logger.exception("Hook before '%s' failed", stage_name)

    async def fire_after(self, stage_name: str, context: PipelineContext) -> None:
        for cb in self._after.get(stage_name, []):
            try:
                cb(stage_name, context)
            except Exception:
                logger.exception("Hook after '%s' failed", stage_name)
