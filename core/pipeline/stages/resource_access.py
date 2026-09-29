"""ResourceAccessStage — the single authority on resource access.

Reads:
  context.resource_scope          — the ResourceScope under check
  context.identity                — IdentityContext snapshot
  context.resource_grant          — issued grant (optional; expiry wins)
  context.metadata["resource_action"] — requested action (default "read")

Writes:
  context.resource_access_result  — frozen ResourceAccessResult

Visibility matrix (the only place these decisions may live — Rules 21/22):

  PRIVATE    owner ✓        non-owner ✗
  WORKSPACE  same tenant+ws ✓  otherwise ✗
  TENANT     same tenant ✓   otherwise ✗
  PUBLIC     everyone ✓ (even with no identity)
  SYSTEM     SYSTEM identity ✓ overrides any scope
"""
from __future__ import annotations

from typing import Any, Optional

from core.identity.models import AuthenticationState
from core.identity.resource_scope import Visibility
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext
from core.pipeline.resource_access_result import ResourceAccessResult

DEFAULT_ACTION = "read"


def _is_system(identity: Any) -> bool:
    state = getattr(identity, "authentication_state", None)
    return getattr(state, "value", state) == AuthenticationState.SYSTEM.value


class ResourceAccessStage(PipelineStage):
    """Evaluates the resource scope and records the access decision."""

    @property
    def name(self) -> str:
        return "resource_access"

    async def execute(self, context: PipelineContext) -> StageResult:
        action = (context.metadata or {}).get("resource_action") or DEFAULT_ACTION
        scope = getattr(context, "resource_scope", None)

        if scope is None:
            return self._record(context, False, "no resource scope", None, action,
                                None)

        # An expired grant overrides everything, including PUBLIC.
        grant = getattr(context, "resource_grant", None)
        if grant is not None and hasattr(grant, "is_expired") and grant.is_expired():
            return self._record(context, False, "resource grant expired", scope,
                                action, None)

        identity = getattr(context, "identity", None)

        # System (scheduler/internal) identities bypass the matrix entirely.
        if _is_system(identity):
            return self._record(context, True, "system identity", scope, action,
                                Visibility.SYSTEM)

        visibility = getattr(scope, "visibility", None)
        if visibility == Visibility.PUBLIC:
            return self._record(context, True, "public resource", scope, action,
                                Visibility.PUBLIC)
        if visibility == Visibility.PRIVATE:
            if self._owns(identity, scope):
                return self._record(context, True, "owner access granted", scope,
                                    action, Visibility.PRIVATE)
            return self._record(context, False, "non-owner access denied", scope,
                                action, Visibility.PRIVATE)
        if visibility == Visibility.TENANT:
            if self._same_tenant(context, identity, scope):
                return self._record(context, True, "same tenant", scope, action,
                                    Visibility.TENANT)
            return self._record(context, False, "cross-tenant access denied", scope,
                                action, Visibility.TENANT)
        if visibility == Visibility.WORKSPACE:
            if self._same_workspace(context, identity, scope):
                return self._record(context, True, "same workspace", scope, action,
                                    Visibility.WORKSPACE)
            return self._record(context, False, "cross-workspace access denied",
                                scope, action, Visibility.WORKSPACE)
        return self._record(context, False, "no visibility rule", scope, action,
                            visibility)

    # ── decision helpers ────────────────────────────────────────────
    @staticmethod
    def _record(context: PipelineContext, allowed: bool, reason: str,
                scope: Any, action: str, visibility: Any) -> StageResult:
        context.resource_access_result = ResourceAccessResult(
            allowed=allowed,
            reason=reason,
            resource_scope=scope,
            requested_action=action,
            effective_visibility=visibility,
        )
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    @staticmethod
    def _owns(identity: Any, scope: Any) -> bool:
        user = getattr(identity, "user", None)
        owner = getattr(scope, "owner_id", None)
        return bool(user is not None and owner and getattr(user, "id", None) == owner)

    @staticmethod
    def _identity_tenant_id(context: PipelineContext, identity: Any) -> Optional[str]:
        tenant = getattr(identity, "tenant", None)
        tenant_id = getattr(tenant, "id", None) or getattr(context, "tenant_id", None)
        return tenant_id or None

    @classmethod
    def _same_tenant(cls, context: PipelineContext, identity: Any,
                     scope: Any) -> bool:
        scope_tenant = getattr(scope, "tenant_id", None)
        identity_tenant = cls._identity_tenant_id(context, identity)
        return bool(scope_tenant and identity_tenant == scope_tenant)

    @classmethod
    def _same_workspace(cls, context: PipelineContext, identity: Any,
                        scope: Any) -> bool:
        if not cls._same_tenant(context, identity, scope):
            return False
        tenant = getattr(identity, "tenant", None)
        identity_ws = getattr(tenant, "workspace_id", None) \
            or getattr(context, "workspace_id", None)
        scope_ws = getattr(scope, "workspace_id", None)
        return bool(scope_ws and identity_ws == scope_ws)


__all__ = ["ResourceAccessStage"]
