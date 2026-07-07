from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.pipeline.context import PipelineContext


@dataclass
class ArchitectureMetrics:
    """Per-request architecture metrics, populated after pipeline execution.

    These are structural measurements of the request's path through the
    architecture — not performance timings.  A separate ``MetricsCollector``
    (not part of this dataclass) aggregates across requests.
    """

    reasoning_complexity: str = "unknown"
    """Output of the Reasoner stage (e.g. ``"simple"``, ``"multi_step"``)."""

    plan_steps: int = 0
    """Number of steps in the logical plan."""

    selected_capabilities: int = 0
    """Number of capability bindings made."""

    observations: int = 0
    """Number of Observations produced by the Execution stage."""

    verifiers: int = 0
    """Number of verifier checks that ran."""

    memory_operations: int = 0
    """Number of memory operations (extractions, writes, contradictions)."""

    activity_depth: int = 0
    """Depth of the Activity span tree (0 if no Activity created)."""

    retries: int = 0
    """Total retries across all stages."""

    execution_state: str = "pending"
    """Final execution state: completed, failed, short_circuited, etc."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoning_complexity": self.reasoning_complexity,
            "plan_steps": self.plan_steps,
            "selected_capabilities": self.selected_capabilities,
            "observations": self.observations,
            "verifiers": self.verifiers,
            "memory_operations": self.memory_operations,
            "activity_depth": self.activity_depth,
            "retries": self.retries,
            "execution_state": self.execution_state,
        }

    @staticmethod
    def from_context(ctx: PipelineContext) -> ArchitectureMetrics:
        """Extract architecture metrics from a completed PipelineContext."""

        plan = ctx.plan or {}
        reasoning = ctx.reasoning_assessment or {}
        verification = ctx.verification_result or {}
        outcome = ctx.outcome

        return ArchitectureMetrics(
            reasoning_complexity=reasoning.get("complexity", "unknown"),
            plan_steps=len(plan.get("steps", [])),
            selected_capabilities=len(ctx.selected_capabilities or {}),
            observations=len(outcome.observations) if outcome else 0,
            verifiers=len(verification.get("verdicts", [])),
            memory_operations=1 if ctx.store_decision else 0,
            activity_depth=1 if ctx.activity_id else 0,
            retries=0,  # populated by Pipeline.execute retry tracking
            execution_state=ctx.execution_state,
        )
