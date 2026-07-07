"""Authentication stage — validates caller identity via IdentityService.

Produces an ``AuthenticationResult`` and transitions ``IdentityContext``
from ``IDENTIFIED`` / ``ANONYMOUS`` to ``AUTHENTICATED`` when token
validation succeeds.

Only this stage may transition ``AuthenticationState`` or construct
``AuthenticationResult``.
"""
from __future__ import annotations

from core.identity import get_identity_service
from core.identity.models import AuthenticationState, IdentityContext
from core.pipeline.authentication_result import AuthenticationResult
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class AuthenticationStage(PipelineStage):
    """Verify caller identity.

    Reads ``context.identity`` and an optional ``auth_token`` from
    ``context.metadata``.  When a token is present, validates it via
    ``IdentityService.authenticate_session()`` and transitions the
    identity to ``AUTHENTICATED``.

    Always produces an ``AuthenticationResult`` on the context.
    """

    @property
    def name(self) -> str:
        return "authentication"

    async def execute(self, context: PipelineContext) -> StageResult:
        identity = context.identity
        token: str | None = context.metadata.get("auth_token")

        if identity is None:
            context.authentication_result = AuthenticationResult(
                authenticated=False,
                state=AuthenticationState.ANONYMOUS,
                reason="no identity context",
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # SYSTEM identity is already authenticated (scheduler, internal)
        if identity.authentication_state == AuthenticationState.SYSTEM:
            context.authentication_result = AuthenticationResult(
                authenticated=True,
                state=AuthenticationState.SYSTEM,
                principal=identity.user,
                session=identity.session,
                reason="system identity",
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # Try token validation
        if token:
            result = get_identity_service().authenticate_session(token)
            if result is not None:
                user, session = result
                new_identity = IdentityContext(
                    user=user,
                    session=session,
                    agent=identity.agent,
                    tenant=identity.tenant,
                    authentication_state=AuthenticationState.AUTHENTICATED,
                )
                context.identity = new_identity
                context.authentication_result = AuthenticationResult(
                    authenticated=True,
                    state=AuthenticationState.AUTHENTICATED,
                    principal=user,
                    session=session,
                )
                return StageResult(outcome=StageOutcome.CONTINUE, context=context)

            # Token present but invalid
            context.authentication_result = AuthenticationResult(
                authenticated=False,
                state=identity.authentication_state,
                reason="invalid or expired token",
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # No token — keep current state (ANONYMOUS or IDENTIFIED)
        context.authentication_result = AuthenticationResult(
            authenticated=False,
            state=identity.authentication_state,
            reason="no authentication token provided",
        )
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
