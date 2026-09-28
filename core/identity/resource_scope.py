"""Resource and visibility scope models.

``ResourceScope`` is the frozen ownership marker carried on every runtime
artifact (observations, outcomes, metrics). Invariants are enforced at
construction time so an invalid scope can never enter the graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Visibility(str, Enum):
    """Who may see a resource.

    Ordering is significant (narrowest → widest, plus the reserved system
    tier); tests assert the declaration order.
    """

    PRIVATE = "private"
    TENANT = "tenant"
    WORKSPACE = "workspace"
    PUBLIC = "public"
    SYSTEM = "system"


#: Migration sentinel for rows/artifacts that predate tenancy.
DEFAULT_TENANT_ID = "__default__"

#: Reserved tenant for system-owned artifacts.
SYSTEM_TENANT_ID = "__system__"


@dataclass(frozen=True)
class ResourceScope:
    """Logical partition key: resources/events belong to a tenant+scope."""

    tenant_id: str = DEFAULT_TENANT_ID
    user_id: Optional[str] = None
    owner_id: Optional[str] = None
    workspace_id: Optional[str] = None
    visibility: Visibility = Visibility.TENANT
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if self.visibility is Visibility.SYSTEM:
            raise ValueError(
                "SYSTEM visibility is reserved and cannot be set on a resource")
        if self.visibility is Visibility.PRIVATE and not self.owner_id:
            raise ValueError("PRIVATE visibility requires an owner_id")
        if self.visibility is Visibility.WORKSPACE and not self.workspace_id:
            raise ValueError("WORKSPACE visibility requires a workspace_id")
        if self.visibility is Visibility.PUBLIC and self.workspace_id is not None:
            raise ValueError(
                "PUBLIC visibility conflicts with a non-None workspace_id")

    # ── helpers ─────────────────────────────────────────────────────
    def is_system(self) -> bool:
        return self.tenant_id == SYSTEM_TENANT_ID

    def is_default(self) -> bool:
        return self.tenant_id == DEFAULT_TENANT_ID

    def matches(self, other: "ResourceScope") -> bool:
        """Same-tenant match (public scopes match across tenants)."""
        if self.visibility == Visibility.PUBLIC or \
                other.visibility == Visibility.PUBLIC:
            return True
        return self.tenant_id == other.tenant_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "owner_id": self.owner_id,
            "workspace_id": self.workspace_id,
            "visibility": self.visibility.value,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (f"ResourceScope(tenant_id={self.tenant_id!r}, "
                f"visibility={self.visibility.value!r})")


def default_scope(**kwargs: Any) -> ResourceScope:
    """Build a default (tenant-scoped) resource scope.

    Construction belongs to this definition module and to the pipeline's
    ``process_message()``; other modules should ask for a scope here rather
    than instantiating one themselves (architecture Rule 19).
    """
    return ResourceScope(**kwargs)


__all__ = ["ResourceScope", "Visibility", "DEFAULT_TENANT_ID",
           "SYSTEM_TENANT_ID", "default_scope"]
