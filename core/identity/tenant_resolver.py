"""Tenant resolution — canonical tenant lookup, inheritance, defaults, validation.

``TenantResolutionResult`` is produced once by ``TenantResolutionStage`` and
read by all downstream stages.  It freezes the answer to "which tenant does
this request belong to?" after authentication has run.

Sprint 6: structural resolution only — no storage backends, no DB lookups.
Actual tenant-scoped storage belongs in later sprints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from core.identity.models import IdentityContext
from core.identity.resource_scope import DEFAULT_TENANT_ID


@dataclass(frozen=True)
class TenantResolutionResult:
    """Canonical tenant assignment for a single request.

    Produced once by ``TenantResolutionStage`` after authentication has run.
    All downstream stages (authorization, resource_access, execution, memory)
    read this result instead of re-resolving the tenant from raw identity fields.
    """

    tenant_id: str
    """Canonical tenant ID after resolution.  Never empty."""

    organization_id: str | None = None
    """Organization within the tenant, if applicable."""

    workspace_id: str | None = None
    """Workspace within the tenant, if applicable."""

    source: str = "default"
    """How the tenant was determined.

    One of:
    - ``"identity"`` — taken directly from ``IdentityContext.tenant.id``
    - ``"authentication"`` — resolved from the authenticated user's tenant binding
    - ``"inheritance"`` — inherited from organization or workspace
    - ``"default"`` — fallback to ``DEFAULT_TENANT_ID``
    """

    valid: bool = True
    """Whether the tenant is active and valid for this request."""

    reason: str | None = None
    """Human-readable explanation of the resolution outcome."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extensible bag for future resolution dimensions."""

    def __hash__(self) -> int:
        return hash((self.tenant_id, self.organization_id, self.workspace_id, self.source, self.valid))


class TenantResolver(Protocol):
    """Canonical tenant resolution protocol.

    Implementations answer "which tenant owns this request?" without
    performing storage partitioning, permission checks, or persistence.
    """

    def resolve_tenant(
        self,
        identity: IdentityContext,
    ) -> TenantResolutionResult:
        """Resolve the canonical tenant for *identity*.

        Args:
            identity: The resolved identity for the current request.

        Returns:
            A ``TenantResolutionResult`` with the canonical tenant assignment.
        """
        ...


class DefaultTenantResolver:
    """Default tenant resolver — structural mapping only.

    Resolution rules (in priority order):

    1. If ``identity.tenant.id`` is set and non-empty, use it directly
       (source: ``"identity"``).
    2. If the identity is authenticated and the resolved user carries
       organization info, inherit from the organization (source: ``"authentication"``).
       *Not yet implemented — requires user DB lookups.*
    3. Fall back to ``DEFAULT_TENANT_ID`` sentinel (source: ``"default"``).
    """

    def resolve_tenant(
        self,
        identity: IdentityContext,
    ) -> TenantResolutionResult:
        if identity is None:
            return TenantResolutionResult(
                tenant_id=DEFAULT_TENANT_ID,
                source="default",
                valid=True,
                reason="no identity — default tenant",
            )

        tenant = identity.tenant

        # Rule 1: explicit tenant ID on identity
        if tenant.id is not None and tenant.id.strip():
            return TenantResolutionResult(
                tenant_id=tenant.id,
                organization_id=tenant.organization_id,
                workspace_id=tenant.workspace_id,
                source="identity",
                valid=True,
                reason=f"resolved from identity tenant id={tenant.id}",
            )

        # Rule 2: authenticated user with org info (placeholder — needs user DB)
        # if identity.user and identity.user.organization_id:
        #     ...

        # Rule 3: fallback to default
        return TenantResolutionResult(
            tenant_id=DEFAULT_TENANT_ID,
            source="default",
            valid=True,
            reason="no tenant information — using default",
        )
