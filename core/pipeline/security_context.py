"""SecurityContext — read-only aggregate of one request's security state.

Snapshot semantics: ``PipelineContext.security`` builds a fresh frozen
``SecurityContext`` on every access, so a context read earlier in the pipeline
never changes retroactively when later stages populate more fields.

Holds no logic and no decisions: every field is produced by its owning stage
(authentication, tenant_resolution, authorization, resource_access).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def _dump(value: Any) -> Any:
    return value.to_dict() if hasattr(value, "to_dict") else value


@dataclass(frozen=True)
class SecurityContext:
    """Frozen view over identity + authentication + authorization + access."""

    identity: Any = None
    authentication: Any = None
    authorization: Any = None
    resource_scope: Any = None
    resource_access: Any = None
    resource_grant: Any = None
    tenant_resolution: Any = None
    # Convenience mirrors (derived from resource_scope when available).
    tenant_id: Optional[str] = None
    workspace_id: Optional[str] = None
    owner_id: Optional[str] = None
    visibility: Optional[str] = None
    scopes: frozenset = frozenset()

    def __post_init__(self) -> None:
        scope = self.resource_scope
        if scope is None:
            return
        if self.tenant_id is None:
            object.__setattr__(self, "tenant_id", getattr(scope, "tenant_id", None))
        if self.workspace_id is None:
            object.__setattr__(self, "workspace_id",
                               getattr(scope, "workspace_id", None))
        if self.owner_id is None:
            object.__setattr__(self, "owner_id", getattr(scope, "owner_id", None))
        if self.visibility is None:
            visibility = getattr(scope, "visibility", None)
            object.__setattr__(self, "visibility",
                               getattr(visibility, "value", visibility))

    @property
    def authenticated(self) -> bool:
        """True when the request carries a validated principal."""
        return bool(getattr(self.authentication, "authenticated", False))

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "owner_id": self.owner_id,
            "visibility": self.visibility,
            "resource_scope": _dump(self.resource_scope),
            "tenant_resolution": _dump(self.tenant_resolution),
            "authentication": _dump(self.authentication),
            "authorization": _dump(self.authorization),
            "resource_access": _dump(self.resource_access),
            "resource_grant": _dump(self.resource_grant),
            "scopes": sorted(self.scopes),
        }


__all__ = ["SecurityContext"]
