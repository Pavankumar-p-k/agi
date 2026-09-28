"""TenantResolutionStage — resolves the tenant partition for the request."""
from __future__ import annotations

from dataclasses import replace

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext
from core.identity.resource_scope import DEFAULT_TENANT_ID
from core.identity.tenant_resolver import (
    DefaultTenantResolver,
    TenantResolutionResult,
)


class TenantResolutionStage(PipelineStage):
    @property
    def name(self) -> str:
        return "tenant_resolution"

    async def execute(self, context: PipelineContext) -> StageResult:
        identity = getattr(context, "identity", None)
        resolver = DefaultTenantResolver()
        if identity is not None:
            result = resolver.resolve_tenant(identity)
        else:
            result = TenantResolutionResult(
                tenant_id=DEFAULT_TENANT_ID, source="default", valid=True,
                reason="no identity")

        context.tenant_id = result.tenant_id
        context.tenant_resolution_result = result

        # Keep the resource scope in sync with the resolved tenant.
        scope = getattr(context, "resource_scope", None)
        if scope is not None and getattr(scope, "tenant_id", "") != result.tenant_id:
            context.resource_scope = replace(scope, tenant_id=result.tenant_id)
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["TenantResolutionStage"]
