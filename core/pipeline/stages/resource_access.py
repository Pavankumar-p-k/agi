"""Resource Access stage — evaluates whether the current identity may access
the resource described by ``context.resource_scope``.

Produces a ``ResourceAccessResult`` and stores it on the context.
Never mutates ``context.identity`` or ``context.resource_scope``.

Only this stage may construct ``ResourceAccessResult``.

Consumes ``context.resource_grant`` (if present) to verify grant validity:
expired grants cause denial regardless of visibility.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.identity.models import AuthenticationState
from core.identity.resource_scope import ResourceScope, Visibility
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.resource_access_result import ResourceAccessResult


class ResourceAccessStage(PipelineStage):
    """Evaluate whether the current identity may access the resource described
    by ``context.resource_scope``.

    Reads ``context.identity`` and ``context.resource_scope``.
    The requested action is read from ``context.metadata["resource_action"]``
    (defaults to ``"read"``).

    Produces ``context.resource_access_result``.
    """

    @property
    def name(self) -> str:
        return "resource_access"

    async def execute(self, context: PipelineContext) -> StageResult:
        identity = context.identity
        scope = context.resource_scope
        action = context.metadata.get("resource_action", "read")

        # Check grant expiry when a ResourceGrant exists
        grant = context.resource_grant
        if grant is not None and grant.expires_at is not None:
            if datetime.now(timezone.utc) >= grant.expires_at:
                context.resource_access_result = ResourceAccessResult(
                    allowed=False,
                    reason="resource grant expired",
                    resource_scope=scope or ResourceScope(tenant_id=""),
                    requested_action=action,
                    effective_visibility=(
                        scope.visibility if scope else Visibility.PRIVATE
                    ),
                )
                return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # No resource scope — no resource to protect
        if scope is None:
            context.resource_access_result = ResourceAccessResult(
                allowed=False,
                reason="no resource scope",
                resource_scope=ResourceScope(tenant_id=""),
                requested_action=action,
                effective_visibility=Visibility.PRIVATE,
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # SYSTEM identity — always allowed
        if identity is not None and identity.authentication_state == AuthenticationState.SYSTEM:
            context.resource_access_result = ResourceAccessResult(
                allowed=True,
                reason="system identity",
                resource_scope=scope,
                requested_action=action,
                effective_visibility=Visibility.SYSTEM,
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # Evaluate by visibility
        if scope.visibility == Visibility.PUBLIC:
            context.resource_access_result = ResourceAccessResult(
                allowed=True,
                reason="public resource",
                resource_scope=scope,
                requested_action=action,
                effective_visibility=Visibility.PUBLIC,
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        if scope.visibility == Visibility.TENANT:
            allowed = (
                identity is not None
                and identity.tenant is not None
                and identity.tenant.id == scope.tenant_id
            )
            context.resource_access_result = ResourceAccessResult(
                allowed=allowed,
                reason="same tenant" if allowed else "cross-tenant access denied",
                resource_scope=scope,
                requested_action=action,
                effective_visibility=Visibility.TENANT,
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        if scope.visibility == Visibility.WORKSPACE:
            allowed = (
                identity is not None
                and identity.tenant is not None
                and identity.tenant.id == scope.tenant_id
                and identity.tenant.workspace_id is not None
                and identity.tenant.workspace_id == scope.workspace_id
            )
            context.resource_access_result = ResourceAccessResult(
                allowed=allowed,
                reason="same workspace" if allowed else "cross-workspace access denied",
                resource_scope=scope,
                requested_action=action,
                effective_visibility=Visibility.WORKSPACE,
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        if scope.visibility == Visibility.PRIVATE:
            allowed = (
                identity is not None
                and identity.user is not None
                and identity.user.id is not None
                and identity.user.id == scope.owner_id
            )
            context.resource_access_result = ResourceAccessResult(
                allowed=allowed,
                reason="owner access granted" if allowed else "non-owner access denied",
                resource_scope=scope,
                requested_action=action,
                effective_visibility=Visibility.PRIVATE,
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # Unknown visibility — deny
        context.resource_access_result = ResourceAccessResult(
            allowed=False,
            reason=f"unknown visibility: {scope.visibility}",
            resource_scope=scope,
            requested_action=action,
            effective_visibility=scope.visibility,
        )
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
