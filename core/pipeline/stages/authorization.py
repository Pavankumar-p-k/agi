"""AuthorizationStage — decides allowed/denied for a requested scope.

Only this stage (and core/identity/service.py) may construct
AuthorizationResult (architecture audit Rule 16). Reads:

  context.metadata["auth_scope"]  — requested scope string (optional)
  context.identity                — IdentityContext snapshot

Behavior:
  no scope requested                     -> denied, scope="", "no scope requested"
  identity state SYSTEM                  -> allowed, "system identity"
  unknown scope                          -> denied, "unknown scope: <scope>"
  otherwise                              -> IdentityService.authorize()
"""
from __future__ import annotations

from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext
from core.identity.models import AuthenticationState
from core.pipeline.authorization_result import AuthorizationResult


class AuthorizationStage(PipelineStage):
    @property
    def name(self) -> str:
        return "authorization"

    async def execute(self, context: PipelineContext) -> StageResult:
        scope = (context.metadata or {}).get("auth_scope") or ""
        identity = getattr(context, "identity", None)

        if not scope:
            context.authorization_result = AuthorizationResult(
                allowed=False, reason="no scope requested", scope="")
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        state = getattr(identity, "authentication_state", None)
        state_val = getattr(state, "value", state)
        if state_val == AuthenticationState.SYSTEM.value:
            from core.identity.models import UserIdentity
            user = getattr(identity, "user", None) or UserIdentity(
                id="system", roles=["admin"])
            context.authorization_result = AuthorizationResult(
                allowed=True, reason="system identity", scope=scope,
                roles=frozenset({"admin"} | set(getattr(user, "roles", []) or [])),
                permissions=frozenset({scope}),
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        from core.identity.service import get_identity_service
        result = get_identity_service().authorize(identity, scope)
        context.authorization_result = result
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["AuthorizationStage"]
