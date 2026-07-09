"""Read-only aggregation of the per-request security state.

``PipelineContext.security`` exposes a single frozen object combining
all security artifacts so that downstream stages never need to reach
for the individual fields.

Built after ``ResourceAccessStage``.  No stage owns or mutates this
object — it is a derived convenience aggregate, not a source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.identity.models import IdentityContext
from core.identity.resource_scope import ResourceScope
from core.identity.tenant_resolver import TenantResolutionResult
from core.pipeline.authentication_result import AuthenticationResult
from core.pipeline.authorization_result import AuthorizationResult
from core.pipeline.resource_access_result import ResourceAccessResult
from core.pipeline.resource_grant import ResourceGrant


@dataclass(frozen=True)
class SecurityContext:
    """Read-only aggregate of the per-request security state.

    Every field is typed but may be ``None`` before the corresponding
    stage has run.  After ``ResourceAccessStage`` all five fields are
    populated for every request.
    """

    identity: Optional[IdentityContext] = None
    """The resolved identity for the current request (set by load-context)."""

    authentication: Optional[AuthenticationResult] = None
    """The authentication result (set by authentication stage)."""

    authorization: Optional[AuthorizationResult] = None
    """The authorization result (set by authorization stage)."""

    resource_grant: Optional[ResourceGrant] = None
    """The resource grant issued by the authorization stage."""

    resource_scope: Optional[ResourceScope] = None
    """The resource ownership scope for this request (set by process_message)."""

    resource_access: Optional[ResourceAccessResult] = None
    """The resource access result (set by resource access stage)."""

    tenant_resolution: Optional[TenantResolutionResult] = None
    """The tenant resolution result (set by tenant resolution stage)."""
