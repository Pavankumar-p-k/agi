"""Metrics stage.

Aggregates timing, token counts, and retry data collected by earlier
stages and emits them through ``core.event_bus``.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class MetricsStage(PipelineStage):
    """Aggregate and emit observability data for this request."""

    @property
    def name(self) -> str:
        return "metrics"

    async def execute(self, context: PipelineContext) -> StageResult:
        context.metrics.setdefault("intent", context.classification.get("mode", "unknown") if context.classification else "unknown")
        context.metrics.setdefault("provider", context.execution_result.get("provider", "unknown") if context.execution_result else "unknown")
        context.metrics.setdefault("tokens", context.execution_result.get("tokens", 0) if context.execution_result else 0)
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
