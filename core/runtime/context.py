from __future__ import annotations

from dataclasses import dataclass

from core.identity.models import IdentityContext
from core.identity.resource_scope import ResourceScope
from core.identity.tenant_resolver import TenantResolutionResult
from core.pipeline.authentication_result import AuthenticationResult
from core.pipeline.authorization_result import AuthorizationResult
from core.pipeline.resource_grant import ResourceGrant


@dataclass(frozen=True)
class RuntimeContext:
    identity: IdentityContext
    authentication: AuthenticationResult
    authorization: AuthorizationResult
    tenant: TenantResolutionResult
    resource_scope: ResourceScope
    resource_grant: ResourceGrant
    activity_id: str
    request_id: str
