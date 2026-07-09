from __future__ import annotations

from typing import Optional

from core.identity.models import (
    AgentIdentity,
    AuthenticationState,
    IdentityContext,
    SessionIdentity,
    TenantIdentity,
    UserIdentity,
)
from core.identity.resource_scope import ResourceScope, Visibility
from core.identity.service import IdentityResolver, IdentityService
from core.identity.tenant_resolver import (
    DefaultTenantResolver,
    TenantResolutionResult,
    TenantResolver,
)

__all__ = [
    "AgentIdentity",
    "AuthenticationState",
    "DefaultTenantResolver",
    "IdentityContext",
    "IdentityResolver",
    "IdentityService",
    "ResourceScope",
    "SessionIdentity",
    "TenantIdentity",
    "TenantResolutionResult",
    "TenantResolver",
    "UserIdentity",
    "Visibility",
    "get_identity_service",
    "set_identity_service",
]

_identity_service: IdentityResolver | None = None


def get_identity_service() -> IdentityResolver:
    """Return the application-wide identity resolver singleton."""
    global _identity_service
    if _identity_service is None:
        _identity_service = IdentityService()
    return _identity_service


def set_identity_service(service: IdentityResolver) -> None:
    """Override the identity resolver (used in tests)."""
    global _identity_service
    _identity_service = service
