"""LearningStage — canonical post-reflection learning.

Consumes ``ReflectionResult`` (from the Reflection stage) and produces
``LearningRecord`` for the Memory stage.

Pipeline position: after Reflection, before Memory (Sprint 5).
"""
from __future__ import annotations

from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.learning_result import LearningRecord


class LearningStage(PipelineStage):
    """Canonical learning stage.

    Reads reflection data and produces a structured learning record
    that the downstream Memory stage persists.
    """

    @property
    def name(self) -> str:
        return "learning"

    async def execute(self, context: PipelineContext) -> StageResult:
        reflection = context.reflection_result

        if reflection is None:
            # No reflection data — produce an empty record
            context.learning_records = ()
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        learning_id = _make_learning_id(context.services)

        record = LearningRecord(
            learning_id=learning_id,
            activity_id=reflection.activity_id,
            reflection_id=reflection.reflection_id,
            success_rating=reflection.success_rating,
            lessons=reflection.lessons,
            patterns=reflection.patterns,
            strategies_used=reflection.strategies_used,
            total_facts=reflection.total_facts_collected,
            sources_count=reflection.total_sources,
            confidence=reflection.overall_confidence,
            contradictions=reflection.contradictions_found,
            store_decision="store" if reflection.success_rating >= 0.3 else "skip",
        )

        context.learning_records = (record,)

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


def _make_learning_id(services: Any) -> str:
    """Generate a deterministic or random learning id."""
    raw = services.uuid4()
    if isinstance(raw, str):
        return f"lrn_{raw[:24]}"
    return f"lrn_{raw.hex[:24]}"
