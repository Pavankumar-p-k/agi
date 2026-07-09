"""Rate-limit stage — enforces per-user/per-transport rate limits.

Previously a pass-through relying on HTTP middleware.  Now applies
``api_rate_limiter`` at the pipeline level so non-HTTP transports
(WebSocket, CLI, MCP, scheduler) also have rate limiting.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.rate_limiter import api_rate_limiter


class RateLimitStage(PipelineStage):
    """Enforce per-user / per-transport rate limits."""

    @property
    def name(self) -> str:
        return "rate_limit"

    async def execute(self, context: PipelineContext) -> StageResult:
        scope = context.transport or "unknown"
        client_ip = _resolve_client_identifier(context)
        if not api_rate_limiter.check(scope, client_ip):
            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                error="rate_limit_exceeded",
            )
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


def _resolve_client_identifier(context: PipelineContext) -> str:
    if context.identity and context.identity.user_id:
        return context.identity.user_id
    if context.parsed_request and isinstance(context.parsed_request, dict):
        ip = context.parsed_request.get("client_ip") or context.parsed_request.get("ip")
        if ip:
            return str(ip)
    if context.user_id:
        return context.user_id
    return context.request_id
