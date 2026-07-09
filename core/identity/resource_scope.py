"""Canonical resource ownership marker for tenant isolation.

``ResourceScope`` answers "which resources belong together?" — it tags
every persisted runtime artifact with an ownership domain so that
tenant isolation can be enforced without inspecting payload content.

Sprint 4: structural definition and pipeline propagation.  Actual
tenant-scoped storage backends belong in later sprints.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Sentinel ──────────────────────────────────────────────────────────────────

DEFAULT_TENANT_ID = "__default__"
"""Migration sentinel for artifacts that have not been assigned a real tenant.

This value exists only for backward compatibility during Phase 6.
All new artifacts should carry a real tenant ID.  See MIGRATION_BACKLOG.
"""

SYSTEM_TENANT_ID = "__system__"
"""Reserved tenant ID for cluster-internal runtime artifacts
(system metrics, global configuration, built-in capabilities).
"""


# ── Visibility ────────────────────────────────────────────────────────────────


class Visibility(Enum):
    """Who may discover or access this resource.

    Ordered from most to least restrictive.
    """

    PRIVATE = "private"
    """Only the owning user may access this resource."""

    TENANT = "tenant"
    """Any user within the owning tenant may access this resource."""

    WORKSPACE = "workspace"
    """Any user within the owning workspace may access this resource."""

    PUBLIC = "public"
    """Any authenticated user may access this resource."""

    SYSTEM = "system"
    """Only system identities (scheduler, internal). Not a settable
    visibility on user-created resources — used exclusively as an
    effective visibility when the SYSTEM bypass is active."""


# ── ResourceScope ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResourceScope:
    """Ownership domain for a single runtime artifact.

    Every persisted artifact (Observation, Outcome, Memory, Activity,
    Scheduler job, Snapshot, …) belongs to exactly one ``ResourceScope``.

    The combination of ``(tenant_id, workspace_id, owner_id, visibility)``
    is the unit of isolation — not any single field in isolation.
    """

    tenant_id: str
    """The tenant that owns this resource.  Never ``None``."""

    workspace_id: str | None = None
    """Optional workspace within the tenant."""

    owner_id: str | None = None
    """Optional user or agent that created this resource."""

    visibility: Visibility = Visibility.TENANT
    """Default visibility within the tenant."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extensible bag for future isolation dimensions."""

    def __post_init__(self) -> None:
        """Validate invariants that prevent contradictory ownership."""
        if self.visibility == Visibility.PRIVATE and self.owner_id is None:
            raise ValueError(
                "PRIVATE visibility requires an owner_id"
            )
        if self.visibility == Visibility.WORKSPACE and self.workspace_id is None:
            raise ValueError(
                "WORKSPACE visibility requires a workspace_id"
            )
        if self.workspace_id is not None and self.visibility == Visibility.PUBLIC:
            raise ValueError(
                "PUBLIC visibility conflicts with a non-None workspace_id"
            )
        if self.visibility == Visibility.SYSTEM:
            raise ValueError(
                "SYSTEM visibility is reserved for the effective_visibility "
                "field of ResourceAccessResult and must not be set on a "
                "user-created ResourceScope"
            )

    def is_system(self) -> bool:
        """``True`` when this scope targets the reserved system tenant."""
        return self.tenant_id == SYSTEM_TENANT_ID

    def is_default(self) -> bool:
        """``True`` when this scope carries the migration sentinel.

        These artifacts have not yet been assigned a real tenant.
        """
        return self.tenant_id == DEFAULT_TENANT_ID

    def __hash__(self) -> int:
        return hash((self.tenant_id, self.workspace_id, self.owner_id, self.visibility))
