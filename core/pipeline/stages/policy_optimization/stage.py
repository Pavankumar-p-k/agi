"""PolicyOptimizationStage — derives policy suggestions from learning records."""
from __future__ import annotations

import uuid as _uuid

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext
from core.pipeline.policy_optimization_result import PolicyOptimizationResult


class PolicyOptimizationStage(PipelineStage):
    @property
    def name(self) -> str:
        return "policy_optimization"

    async def execute(self, context: PipelineContext) -> StageResult:
        records = tuple(getattr(context, "learning_records", ()) or ())
        if not records:
            context.policy_optimization_result = None
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        record = records[0]
        success = float(getattr(record, "success_rating", 0.0) or 0.0)
        confidence = float(getattr(record, "confidence", 0.0) or 0.0)
        contradictions = int(getattr(record, "contradictions", 0) or 0)
        patterns = tuple(getattr(record, "patterns", ()) or ())
        lessons = tuple(getattr(record, "lessons", ()) or ())
        store_decision = str(getattr(record, "store_decision", "skip"))

        services = getattr(context, "services", None)
        oid = services.uuid4() if services is not None and hasattr(services, "uuid4") \
            else _uuid.uuid4().hex

        if contradictions >= 3 or success < 0.5:
            profile = "strict"
            multiplier, risk_max = 0.5, "low"
            block = tuple(p for p in patterns if success < 0.5) or \
                tuple(p for p in patterns if "risky" in p or "unstable" in p) or patterns
            allow = ()
        elif success >= 0.85 and confidence >= 0.7 and contradictions == 0:
            profile = "autonomous"
            multiplier, risk_max = 2.0, "critical"
            allow = patterns + lessons
            block = ()
        else:
            profile = "standard"
            multiplier, risk_max = 1.0, "medium"
            allow, block = (), ()

        context.policy_optimization_result = PolicyOptimizationResult(
            optimization_id=f"pol_{oid[:24]}",
            activity_id=getattr(record, "activity_id", ""),
            suggested_profile=profile,
            rate_limit_multiplier=multiplier,
            adjusted_risk_max=risk_max,
            allow_patterns=allow,
            block_patterns=block,
            confidence=confidence,
        )
        context.policy_profile = profile
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["PolicyOptimizationStage"]
