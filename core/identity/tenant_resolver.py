"""Tenant resolution — maps identities to a tenant partition."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.identity.resource_scope import DEFAULT_TENANT_ID


@dataclass(frozen=True)
class TenantResolutionResult:
    tenant_id: str = DEFAULT_TENANT_ID
    organization_id: Optional[str] = None
    workspace_id: Optional[str] = None
    source: str = "default"
    valid: bool = True
    reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "source": self.source,
            "valid": self.valid,
        }


class TenantResolver:
    """Interface: resolve(context) -> TenantResolutionResult."""

    def resolve(self, context: Any) -> TenantResolutionResult:
        raise NotImplementedError

    def resolve_tenant(self, identity: Any) -> TenantResolutionResult:
        raise NotImplementedError


class DefaultTenantResolver(TenantResolver):
    """Structural resolution: identity.tenant first, then context fields."""

    def resolve(self, context: Any) -> TenantResolutionResult:
        identity = getattr(context, "identity", None)
        if identity is not None:
            result = self.resolve_tenant(identity)
            if result.source != "default":
                return result
        tenant_id = getattr(context, "tenant_id", None)
        if not tenant_id:
            metadata = getattr(context, "metadata", None) or {}
            tenant_id = metadata.get("tenant_id", DEFAULT_TENANT_ID)
        return TenantResolutionResult(
            tenant_id=str(tenant_id) if tenant_id else DEFAULT_TENANT_ID,
            resolved=True, source="context" if tenant_id else "default",
        )

    def resolve_tenant(self, identity: Any) -> TenantResolutionResult:
        if identity is None:
            return TenantResolutionResult(
                tenant_id=DEFAULT_TENANT_ID, source="default", valid=True,
                reason="no identity")
        tenant = getattr(identity, "tenant", None)
        tid = (getattr(tenant, "id", "") or "").strip() if tenant else ""
        # An empty id, whitespace, or the default placeholder means the
        # identity carries no explicit tenant — resolve structurally.
        if not tid or tid == DEFAULT_TENANT_ID:
            return TenantResolutionResult(
                tenant_id=DEFAULT_TENANT_ID, source="default", valid=True,
                reason="empty tenant id on identity")
        return TenantResolutionResult(
            tenant_id=tid,
            organization_id=getattr(tenant, "organization_id", None),
            workspace_id=getattr(tenant, "workspace_id", None),
            source="identity", valid=True,
        )


__all__ = ["TenantResolver", "DefaultTenantResolver", "TenantResolutionResult"]
