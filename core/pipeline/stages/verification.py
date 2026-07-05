"""Verification stage — currently a pass-through.

Validates execution output for safety, quality, and schema conformance.
Full implementation will integrate with ``core.routing.safety`` and
output validation hooks.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class VerificationStage(PipelineStage):
    """Validate the execution output before it reaches the user.

    **Invariant:** Never calls LLMs, never selects providers.
    Only reads ``context.execution_result`` and writes
    ``context.verification_result``.
    """

    @property
    def name(self) -> str:
        return "verification"

    async def execute(self, context: PipelineContext) -> StageResult:
        context.verification_result = {"passed": True, "checks": []}
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
