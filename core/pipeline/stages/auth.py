"""Authentication stage — currently a pass-through.

Authentication is handled at the HTTP middleware layer (API keys, JWT tokens,
session cookies).  This stage exists in the pipeline for future extension
(e.g. rate-limit overrides, per-user capability gating).
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class AuthenticationStage(PipelineStage):
    """Verify caller identity.

    This stage is intentionally minimal.  Real auth checks happen in the
    transport's HTTP middleware; this stage records the outcome in context.
    """

    @property
    def name(self) -> str:
        return "authentication"

    async def execute(self, context: PipelineContext) -> StageResult:
        context.metadata["authenticated"] = context.user_id is not None
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
