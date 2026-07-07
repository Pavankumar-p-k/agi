"""Authorization stage — evaluates whether an authenticated identity may
perform the requested scope.

Produces an ``AuthorizationResult`` and stores it on the context.
Never mutates ``context.identity``.

Only this stage may construct ``AuthorizationResult``.
"""
from __future__ import annotations

from core.identity import get_identity_service
from core.identity.models import AuthenticationState
from core.identity.scope import CANONICAL_SCOPES
from core.pipeline.authorization_result import AuthorizationResult
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class AuthorizationStage(PipelineStage):
    """Evaluate whether the authenticated identity may perform the requested scope.

    Reads ``context.identity`` and ``context.authentication_result``.
    Produces ``context.authorization_result``.

    Skips evaluation when the scope is not recognised (defers to downstream
    stages).
    """

    @property
    def name(self) -> str:
        return "authorization"

    async def execute(self, context: PipelineContext) -> StageResult:
        identity = context.identity
        scope: str | None = context.metadata.get("auth_scope")

        # No scope requested — nothing to authorise
        if not scope:
            context.authorization_result = AuthorizationResult(
                allowed=False,
                scope="",
                reason="no scope requested",
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # Unknown scope — allow but warn (may be a valid scope unknown to this stage)
        if scope not in CANONICAL_SCOPES:
            context.authorization_result = AuthorizationResult(
                allowed=False,
                scope=scope,
                reason=f"unknown scope: {scope}",
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # No identity — cannot authorise
        if identity is None:
            context.authorization_result = AuthorizationResult(
                allowed=False,
                scope=scope,
                reason="no identity context",
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # SYSTEM identity is always authorised for any scope
        if identity.authentication_state == AuthenticationState.SYSTEM:
            context.authorization_result = AuthorizationResult(
                allowed=True,
                scope=scope,
                reason="system identity",
                roles=frozenset({"system"}),
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # Delegate to IdentityService
        result = get_identity_service().authorize(identity, scope)
        context.authorization_result = result
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
