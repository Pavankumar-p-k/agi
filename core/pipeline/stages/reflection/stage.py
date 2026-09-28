"""ReflectionStage — Rule 52 owner of ReflectionResult construction."""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext
from core.pipeline.reflection_result import ReflectionResult


class ReflectionStage(PipelineStage):
    @property
    def name(self) -> str:
        return "reflection"

    async def execute(self, context: PipelineContext) -> StageResult:
        services = getattr(context, "services", None)
        import uuid as _uuid

        reflection_id = f"ref_{(services.uuid4() if services is not None and hasattr(services, 'uuid4') else _uuid.uuid4().hex)[:24]}"
        rr = getattr(context, "reasoning_result", None)
        beliefs = tuple(getattr(rr, "beliefs", ()) or ()) if rr is not None else ()
        confidence = float(getattr(rr, "confidence", 0.0) or 0.0) if rr is not None else 0.0

        # Success rating: derive deterministically from the plan + beliefs.
        plan = getattr(context, "plan", None)
        steps = plan.get("steps", []) if isinstance(plan, dict) else []
        success_rating = 0.0
        if steps:
            success_rating = min(1.0, 0.5 + 0.1 * len(steps))
        if beliefs:
            success_rating = min(1.0, success_rating + 0.2)
        if not context.raw_input:
            success_rating = 0.0

        context.reflection_result = ReflectionResult(
            reflection_id=reflection_id,
            activity_id=getattr(context, "activity_id", "") or "",
            question=str(getattr(context, "raw_input", "") or ""),
            success_rating=success_rating,
            overall_confidence=confidence,
            lessons=("review plan outcomes",) if steps else (),
            metadata={},
        )
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["ReflectionStage"]
