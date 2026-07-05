"""Epistemic tagging stage.

Tags the execution output with confidence, provenance, and source
attribution metadata.  This enables downstream consumers to reason
about the reliability of the response.
"""
from __future__ import annotations

import time

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class EpistemicTaggingStage(PipelineStage):
    """Tag output with confidence and provenance information."""

    @property
    def name(self) -> str:
        return "epistemic"

    async def execute(self, context: PipelineContext) -> StageResult:
        context.epistemic_tags = {
            "model": context.execution_result.get("provider", "unknown") if context.execution_result else "unknown",
            "confidence": 1.0 if context.error is None else 0.0,
            "timestamp": time.time(),
            "provenance": "execution",
        }
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
