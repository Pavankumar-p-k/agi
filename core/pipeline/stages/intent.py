from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.routing.request_classifier import classify_request


class IntentStage(PipelineStage):
    """Classify the request mode using the canonical classifier.

    Calls ``classify_request()`` from ``core.routing.request_classifier``
    and stores the result on ``context.classification``.

    **Invariant:** This stage never calls an LLM — only keyword matching
    and fast pattern matching.  The LLM fallback in ``classify_request``
    is disabled when confidence is high enough from keywords alone.
    """

    @property
    def name(self) -> str:
        return "intent"

    async def execute(self, context: PipelineContext) -> StageResult:
        text = context.raw_input or ""

        if not text.strip():
            return StageResult(
                outcome=StageOutcome.CONTINUE,
                context=context,
            )

        classification = classify_request(text)

        context.classification = {
            "mode": classification.mode.value if hasattr(classification, "mode") else str(classification.mode),
            "confidence": classification.confidence if hasattr(classification, "confidence") else 0.0,
            "sub_type": classification.sub_type if hasattr(classification, "sub_type") else None,
        }

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
