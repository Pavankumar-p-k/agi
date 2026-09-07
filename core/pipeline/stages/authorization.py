"""Authorization stage."""
from __future__ import annotations

from core.identity.models import AuthenticationState
from core.identity.service import get_identity_service
from core.pipeline.authorization_result import AuthorizationResult
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class AuthorizationStage(PipelineStage):
    @property
    def name(self) -> str:
        return "authorization"

    async def execute(self, context: PipelineContext) -> StageResult:
        scope = ""
        if isinstance(context.metadata, dict):
            scope = str(context.metadata.get("auth_scope", ""))
        if not scope:
            result = AuthorizationResult(allowed=False, scope="", reason="no scope requested")
            context.authorization_result = result
            return StageResult(outcome=StageOutcome.CONTINUE, context=context, authorization_result=result)

        identity = context.identity
        auth_result = context.authentication_result

        if identity is not None and identity.authentication_state == AuthenticationState.SYSTEM:
            result = AuthorizationResult(allowed=True, scope=scope, reason="system identity")
            context.authorization_result = result
            return StageResult(outcome=StageOutcome.CONTINUE, context=context, authorization_result=result)

        if auth_result is not None and not auth_result.authenticated:
            missing_user = identity is None or identity.user is None or not getattr(identity.user, "id", None)
            if missing_user and identity is not None and identity.authentication_state == AuthenticationState.AUTHENTICATED:
                result = AuthorizationResult(allowed=False, scope=scope, reason="no user identity")
            elif missing_user and auth_result.reason == "no identity context":
                result = AuthorizationResult(allowed=False, scope=scope, reason=f"unknown scope: {scope}")
            elif missing_user:
                result = AuthorizationResult(allowed=False, scope=scope, reason=f"unknown scope: {scope}")
            else:
                result = AuthorizationResult(allowed=False, scope=scope, reason=auth_result.reason or "not authenticated")
            context.authorization_result = result
            return StageResult(outcome=StageOutcome.CONTINUE, context=context, authorization_result=result)

        if identity is None or identity.user is None or not getattr(identity.user, "id", None):
            result = AuthorizationResult(allowed=False, scope=scope, reason=f"unknown scope: {scope}")
            context.authorization_result = result
            return StageResult(outcome=StageOutcome.CONTINUE, context=context, authorization_result=result)

        service = get_identity_service()
        result = service.authorize(identity, scope)
        if result is None:
            result = AuthorizationResult(allowed=False, scope=scope, reason=f"unknown scope: {scope}")
        context.authorization_result = result
        return StageResult(outcome=StageOutcome.CONTINUE, context=context, authorization_result=result)
