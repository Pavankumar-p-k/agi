"""Canonical request pipeline — public surface (ADR-006)."""
from __future__ import annotations

from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext as _CompatContext
from core.pipeline.pipeline import (
    Pipeline,
    PipelineContext,
    Request,
    Response,
    STAGE_OWNERSHIP,
    StageOutcome as _StageOutcomeAlias,
)
from core.pipeline.pipeline import get_pipeline, process_message, set_pipeline

# Compatibility re-exports (older modules import these names from here).
Request = Request
Response = Response

# DEFAULT_STAGES lives in the stages package.
from core.pipeline.stages import DEFAULT_STAGES  # noqa: E402,F401

__all__ = [
    "Pipeline", "PipelineContext", "PipelineStage", "Request", "Response",
    "StageOutcome", "StageResult", "STAGE_OWNERSHIP", "DEFAULT_STAGES",
    "get_pipeline", "set_pipeline", "process_message",
]


def __getattr__(name: str) -> Any:
    # Lazy companions (stream/decision/etc.) so importing core.pipeline
    # stays cheap and doesn't crash when a companion module is absent.
    if name == "StreamEvent" or name == "StreamEventType" or name == "stream_pipeline":
        from core.pipeline import stream
        return getattr(stream, name)
    if name == "Decision":
        from core.pipeline import decision
        return decision.Decision
    if name == "Observation":
        from core.pipeline import observation
        return observation.Observation
    if name == "Outcome":
        from core.pipeline import outcome
        return outcome.Outcome
    if name in ("StoreAction", "StoreDecision"):
        from core.pipeline import store_decision
        return getattr(store_decision, name)
    raise AttributeError(f"module 'core.pipeline' has no attribute {name!r}")
