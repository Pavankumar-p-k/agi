"""Tenant Resolution stage — determines the canonical tenant for this request.

Reads the authenticated identity and resolves the tenant ID through
lookup, inheritance, or default fallback.  Produces a
``TenantResolutionResult`` and updates ``context.resource_scope`` with
the resolved tenant information.

Only this stage may construct ``TenantResolutionResult``.
"""
from __future__ import annotations

from core.identity import get_identity_service
from core.identity.models import AuthenticationState
from core.identity.resource_scope import DEFAULT_TENANT_ID, ResourceScope, Visibility
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class TenantResolutionStage(PipelineStage):
    """Resolve the canonical tenant for the current request.

    Reads ``context.identity`` (and optionally ``context.authentication_result``).
    Delegates to ``IdentityService.resolve_tenant()`` for the actual resolution.
    Produces ``context.tenant_resolution_result``.
    """

    @property
    def name(self) -> str:
        return "tenant_resolution"

    async def execute(self, context: PipelineContext) -> StageResult:
        identity = context.identity
        resolver = get_identity_service()
        result = resolver.resolve_tenant(identity)

        context.tenant_resolution_result = result

        # Update resource_scope with the resolved tenant information.
        # The initial resource_scope was created by process_message() with
        # the raw tenant from identity; this stage replaces it with the
        # canonical resolved tenant ID.
        current_scope = context.resource_scope
        if current_scope is not None and result.tenant_id != current_scope.tenant_id:
            context.resource_scope = ResourceScope(
                tenant_id=result.tenant_id,
                workspace_id=result.workspace_id or current_scope.workspace_id,
                owner_id=current_scope.owner_id,
                visibility=current_scope.visibility,
                metadata=dict(current_scope.metadata),
            )

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
