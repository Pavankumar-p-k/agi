"""LearningStage — records learned lessons from reflection results."""
from __future__ import annotations

import uuid as _uuid

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.learning_result import LearningRecord
from core.pipeline.pipeline import PipelineContext


class LearningStage(PipelineStage):
    @property
    def name(self) -> str:
        return "learning"

    async def execute(self, context: PipelineContext) -> StageResult:
        services = getattr(context, "services", None)
        reflection = getattr(context, "reflection_result", None)

        records = []
        if reflection is not None:
            rid = services.uuid4() if services is not None and hasattr(services, "uuid4") \
                else _uuid.uuid4().hex
            success_rating = float(getattr(reflection, "success_rating", 0.0) or 0.0)
            record = LearningRecord(
                learning_id=f"lrn_{rid[:24]}",
                activity_id=getattr(reflection, "activity_id", "")
                or getattr(context, "activity_id", "") or "",
                reflection_id=getattr(reflection, "reflection_id", ""),
                success_rating=success_rating,
                confidence=float(getattr(reflection, "overall_confidence", 0.0) or 0.0),
                patterns=tuple(getattr(reflection, "patterns", ()) or ()),
                lessons=tuple(getattr(reflection, "lessons", ()) or ()),
                store_decision="store" if success_rating >= 0.5 else "skip",
            )
            records.append(record)

        context.learning_records = tuple(records)
        context.learning_result = {"records": len(records)}
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["LearningStage"]
