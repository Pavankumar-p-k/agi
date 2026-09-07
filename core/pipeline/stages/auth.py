"""Authentication stage."""
from __future__ import annotations

from core.identity.models import AuthenticationState, IdentityContext, SessionIdentity, UserIdentity
from core.identity.service import get_identity_service
from core.pipeline.authentication_result import AuthenticationResult
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class AuthenticationStage(PipelineStage):
    @property
    def name(self) -> str:
        return "authentication"

    async def execute(self, context: PipelineContext) -> StageResult:
        identity = context.identity or IdentityContext(authentication_state=AuthenticationState.ANONYMOUS)
        auth_token = context.metadata.get("auth_token") if isinstance(context.metadata, dict) else None
        state = identity.authentication_state

        if state == AuthenticationState.SYSTEM:
            context.identity = identity
            result = AuthenticationResult(
                authenticated=True,
                state=AuthenticationState.SYSTEM,
                principal=identity.user,
                reason="system identity",
                metadata={"token": auth_token},
            )
            context.authentication_result = result
            identity.authentication_state = AuthenticationState.SYSTEM
            return StageResult(outcome=StageOutcome.CONTINUE, context=context, identity=identity, authentication_result=result)

        if auth_token is not None:
            auth_manager = __import__("core.auth", fromlist=["get_auth_manager"]).get_auth_manager()
            if not auth_manager.validate_token(str(auth_token)):
                result = AuthenticationResult(
                    authenticated=False,
                    state=identity.authentication_state,
                    principal=identity.user,
                    reason="invalid or expired token",
                )
                context.identity = identity
                context.authentication_result = result
                return StageResult(outcome=StageOutcome.CONTINUE, context=context, identity=context.identity, authentication_result=result)

            svc = get_identity_service()
            session_result = svc.authenticate_session(str(auth_token))
            if session_result is None:
                result = AuthenticationResult(
                    authenticated=False,
                    state=identity.authentication_state,
                    principal=identity.user,
                    reason="invalid or expired token",
                )
                context.identity = identity
                context.authentication_result = result
                return StageResult(outcome=StageOutcome.CONTINUE, context=context, identity=context.identity, authentication_result=result)

            principal, session = session_result
            identity.user = principal
            identity.session = session
            identity.authentication_state = AuthenticationState.AUTHENTICATED
            result = AuthenticationResult(
                authenticated=True,
                state=AuthenticationState.AUTHENTICATED,
                principal=principal,
                session=session,
                reason=None,
            )
            context.identity = identity
            context.authentication_result = result
            return StageResult(outcome=StageOutcome.CONTINUE, context=context, identity=identity, authentication_result=result)

        if identity is None or (identity.user is None and not getattr(identity, "user_id", None)):
            if identity is not None and identity.authentication_state in (AuthenticationState.AUTHENTICATED, AuthenticationState.IDENTIFIED):
                state = identity.authentication_state
                reason = "no user identity"
            else:
                state = AuthenticationState.ANONYMOUS
                reason = "no identity context"
            result = AuthenticationResult(
                authenticated=False,
                state=state,
                principal=None,
                reason=reason,
            )
            context.identity = identity or IdentityContext(authentication_state=AuthenticationState.ANONYMOUS)
            context.identity.authentication_state = state
            context.authentication_result = result
            return StageResult(outcome=StageOutcome.CONTINUE, context=context, identity=context.identity, authentication_result=result)

        if auth_token is None:
            state = identity.authentication_state if identity.authentication_state != AuthenticationState.ANONYMOUS else AuthenticationState.IDENTIFIED
            if identity.user is not None and getattr(identity.user, "id", None):
                context.identity.authentication_state = state
            result = AuthenticationResult(
                authenticated=False,
                state=state,
                principal=identity.user,
                reason="no authentication token provided",
            )
            context.authentication_result = result
            return StageResult(outcome=StageOutcome.CONTINUE, context=context, identity=context.identity, authentication_result=result)

        result = AuthenticationResult(
            authenticated=False,
            state=identity.authentication_state,
            principal=identity.user,
            reason="invalid or expired token",
        )
        context.authentication_result = result
        return StageResult(outcome=StageOutcome.CONTINUE, context=context, identity=context.identity, authentication_result=result)
