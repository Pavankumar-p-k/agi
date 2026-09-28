"""Pipeline stage base classes — canonical StageOutcome/StageResult live here.

The contract (tests/architecture/test_pipeline_contract.py) imports
StageOutcome from core.pipeline.base with these members:
  CONTINUE | SHORT_CIRCUIT | RETRY | FAIL | DEFER | CANCELLED
plus STAGE_OWNERSHIP (field-ownership map, ADR-006 §field ownership).
"""
from __future__ import annotations

from dataclasses import dataclass, field  # noqa: F401 — dataclass used below
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from core.pipeline.pipeline import PipelineContext


class StageOutcome(str, Enum):
    CONTINUE = "continue"
    SHORT_CIRCUIT = "short_circuit"
    RETRY = "retry"
    FAIL = "fail"
    DEFER = "defer"
    CANCELLED = "cancelled"


# Fields each canonical stage owns (ADR-006 field-ownership map).
STAGE_OWNERSHIP: dict[str, list[str]] = {
    "receive": ["raw_input", "parsed_request"],
    "load_context": ["metadata.transport", "resource_scope"],
    "authentication": ["authentication_result"],
    "tenant_resolution": ["tenant_id", "tenant_resolution_result"],
    "authorization": ["authorization_result"],
    "resource_access": ["resource_access_result"],
    "rate_limit": ["rate_limit_result"],
    "intent": ["classification"],
    "context_retrieval": ["retrieved_context"],
    "knowledge": ["knowledge_result"],
    "reasoning": ["reasoning_assessment", "reasoning_result"],
    "planner": ["plan", "planner_result"],
    "plan_validator": ["plan_validated"],
    "activity": ["activity_id"],
    "capability_selection": ["selected_capabilities"],
    "execution": ["execution_result", "execution_state"],
    "verification": ["verification_result"],
    "epistemic": ["epistemic_tags"],
    "reflection": ["reflection_result"],
    "learning": ["learning_result"],
    "policy_optimization": ["policy_result"],
    "memory": ["memory_refs"],
    "notification": ["notification_result"],
    "metrics": ["metrics"],
    "explainability": ["explainability_result"],
    "formatter": ["formatted_response"],
}


@dataclass
class StageResult:
    outcome: StageOutcome = StageOutcome.CONTINUE
    context: Optional["PipelineContext"] = None
    error: Optional[str] = None
    metrics: dict = field(default_factory=dict)
    retry_count: int = 0
    metadata: dict = field(default_factory=dict)


# Backwards-compatible alias used by older stage implementations.
PipelineStageResult = StageResult


class PipelineStageMeta(type):
    """Metaclass making PipelineStage abstract (execute must be overridden)."""

    def __call__(cls, *args, **kwargs):
        if cls is PipelineStage:
            raise TypeError(
                "PipelineStage is abstract: override execute() in a subclass")
        if "execute" not in cls.__dict__ and cls.__name__ not in (
                "ReasonerStage",):  # subclasses must implement execute
            for base in cls.__mro__[1:]:
                if "execute" in base.__dict__ and base is not PipelineStage:
                    break
            else:
                raise TypeError(
                    f"{cls.__name__} must implement execute()")
        return super().__call__(*args, **kwargs)


class PipelineStage(metaclass=PipelineStageMeta):
    """Base class for canonical pipeline stages (abstract)."""

    max_retries: int = 1
    timeout: Optional[float] = None

    @property
    def name(self) -> str:
        return type(self).__name__.replace("Stage", "").lower()

    async def execute(self, context: Any) -> StageResult:
        raise NotImplementedError
