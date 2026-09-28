"""ReasoningStage — the single Reasoner abstraction (audit Rule 6).

Complexity assessment plus the one place allowed to construct a
``ReasoningResult`` (Rule 48).
"""
from __future__ import annotations

import re

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext
from core.pipeline.reasoning_result import Belief, ReasoningResult

_SIMPLE_MAX_CHARS = 120
_MULTI_STEP_RE = re.compile(
    r"\b(research|compare|analyz|design|plan|implement|investigate|"
    r"evaluate|multi.?step)\b", re.IGNORECASE)


class ReasoningStage(PipelineStage):
    @property
    def name(self) -> str:
        return "reasoning"

    def assess_complexity(self, text: str) -> str:
        if not text:
            return "simple"
        if len(text) > _SIMPLE_MAX_CHARS or _MULTI_STEP_RE.search(text):
            return "multi_step"
        return "simple"

    async def execute(self, context: PipelineContext) -> StageResult:
        text = str(getattr(context, "raw_input", "") or "")
        complexity = self.assess_complexity(text)
        services = getattr(context, "services", None)
        import uuid as _uuid

        rid_raw = services.uuid4() if services is not None and hasattr(services, "uuid4") \
            else _uuid.uuid4().hex
        rid = f"rsn_{rid_raw[:24]}"

        confidence = 0.9 if complexity == "simple" else 0.7
        belief = Belief(belief_id=f"{rid[:16]}_b1",
                        claim=text[:120] or "empty request",
                        confidence=confidence, status="accepted")
        context.reasoning_result = ReasoningResult(
            reasoning_id=rid,
            activity_id=getattr(context, "activity_id", "") or "",
            complexity=complexity,
            beliefs=(belief,),
            evidence=(),
            contradictions=(),
            counter_hypotheses=(),
            confidence=confidence,
        )
        context.reasoning_assessment = {
            "complexity": complexity, "confidence": confidence,
        }
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


#: Historical name for :class:`ReasoningStage` (Rule 6 named the abstraction
#: ``ReasonerStage``; the canonical class name now matches the stage).
ReasonerStage = ReasoningStage

__all__ = ["ReasoningStage", "ReasonerStage"]
