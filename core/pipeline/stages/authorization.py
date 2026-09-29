"""AuthorizationStage — decides allowed/denied for a requested scope.

Only this stage (and core/identity/service.py) may construct
AuthorizationResult (architecture audit Rule 16), and only this stage issues
a ResourceGrant. Reads:

  context.metadata["auth_scope"]  — requested scope string (optional)
  context.identity                — IdentityContext snapshot

Behavior:
  no scope requested                     -> denied, scope="", "no scope requested"
  identity state SYSTEM                  -> allowed, "system identity"
  unknown scope                          -> denied, "unknown scope: <scope>"
  otherwise                              -> IdentityService.authorize()

Writes:
  context.authorization_result
  context.resource_grant  — issued only when the request is allowed
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from core.identity.models import AuthenticationState
from core.pipeline.authorization_result import AuthorizationResult
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext


class AuthorizationStage(PipelineStage):
    @property
    def name(self) -> str:
        return "authorization"

    async def execute(self, context: PipelineContext) -> StageResult:
        scope = (context.metadata or {}).get("auth_scope") or ""
        identity = getattr(context, "identity", None)

        if not scope:
            result = AuthorizationResult(
                allowed=False, reason="no scope requested", scope="")
            return self._record(context, result, scope)

        state = getattr(identity, "authentication_state", None)
        state_val = getattr(state, "value", state)
        if state_val == AuthenticationState.SYSTEM.value:
            from core.identity.models import UserIdentity
            user = getattr(identity, "user", None) or UserIdentity(
                id="system", roles=["admin"])
            result = AuthorizationResult(
                allowed=True, reason="system identity", scope=scope,
                roles=frozenset({"admin"} | set(getattr(user, "roles", []) or [])),
                permissions=frozenset({scope}),
            )
            return self._record(context, result, scope)

        from core.identity.service import get_identity_service
        result = get_identity_service().authorize(identity, scope)
        return self._record(context, result, scope)

    # ── helpers ─────────────────────────────────────────────────────
    def _record(self, context: PipelineContext,
                result: AuthorizationResult, scope: str) -> StageResult:
        context.authorization_result = result
        context.resource_grant = (
            self._issue_grant(context, result, scope) if result.allowed else None
        )
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    def _issue_grant(self, context: PipelineContext,
                     result: AuthorizationResult, scope: str):
        """Mint the tenant-scoped grant for an allowed request."""
        from core.pipeline.resource_grant import ResourceGrant

        permissions = frozenset(getattr(result, "permissions", None) or {scope})
        subject_id = self._subject_id(context)
        return ResourceGrant(
            subject_id=subject_id,
            scope=getattr(context, "resource_scope", None),
            permissions=permissions,
            issued_at=self._now(context),
            metadata={"reason": getattr(result, "reason", "") or ""},
        )

    @staticmethod
    def _subject_id(context: PipelineContext) -> str:
        user = getattr(getattr(context, "identity", None), "user", None)
        return str(
            getattr(user, "id", "") or context.user_id
            or getattr(getattr(context, "authentication_result", None), "user_id", "")
            or ""
        )

    @staticmethod
    def _now(context: PipelineContext) -> datetime:
        services = getattr(context, "services", None)
        if services is not None and hasattr(services, "now"):
            return services.now()
        return datetime.now(timezone.utc)


__all__ = ["AuthorizationStage"]
