"""Rate-limit stage — enforces per-user/per-transport rate limits.

Previously a pass-through relying on HTTP middleware.  Now applies
``api_rate_limiter`` at the pipeline level so non-HTTP transports
(WebSocket, CLI, MCP, scheduler) also have rate limiting.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.rate_limiter import SlidingWindowRateLimiter, api_rate_limiter


# Per-profile rate limit configurations (max_requests per 60s window)
_PROFILE_LIMITS: dict[str, int] = {
    "strict": 30,
    "developer": 60,
    "autonomous": 120,
}


class RateLimitStage(PipelineStage):
    """Enforce per-user / per-transport rate limits.

    Rate limits are adjusted based on the active ``policy_profile``
    in the pipeline context (set by PolicyOptimizationStage or loaded
    on pipeline start).
    """

    @property
    def name(self) -> str:
        return "rate_limit"

    async def execute(self, context: PipelineContext) -> StageResult:
        scope = context.transport or "unknown"
        client_ip = _resolve_client_identifier(context)

        limiter = _rate_limiter_for_profile(context.policy_profile)
        if not limiter.check(scope, client_ip):
            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                error="rate_limit_exceeded",
            )
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


def _rate_limiter_for_profile(profile: str) -> SlidingWindowRateLimiter:
    """Return a rate limiter configured for the given policy profile."""
    max_req = _PROFILE_LIMITS.get(profile, 60)
    return SlidingWindowRateLimiter(max_requests=max_req, window_seconds=60.0)


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
