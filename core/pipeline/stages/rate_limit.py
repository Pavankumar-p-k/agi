"""Rate-limit stage — currently a pass-through.

Rate limiting is applied at the HTTP middleware layer via
``core.middleware.rate_limit_middleware``.  This stage exists so that
non-HTTP transports (channels, CLI) can apply their own limits later.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class RateLimitStage(PipelineStage):
    """Enforce per-user / per-transport rate limits."""

    @property
    def name(self) -> str:
        return "rate_limit"

    async def execute(self, context: PipelineContext) -> StageResult:
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
