from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from core.identity.resource_scope import ResourceScope


@dataclass(frozen=True)
class ResourceGrant:
    """An immutable grant representing approved permissions for a resource
    scope.

    Issued by ``AuthorizationStage`` after successful authorization.
    Consumed by ``ResourceAccessStage`` and eventually received by
    ``ExecutionStage``.

    ``ExecutionStage`` must never inspect identity roles, authentication
    state, tenant ids, or visibility directly — it should only consume
    this grant along with the plan and capabilities.
    """

    subject_id: str
    """Identifier of the identity that was authorised (user_id or system)."""

    scope: ResourceScope
    """The resource scope this grant applies to."""

    permissions: frozenset[str] = field(default_factory=frozenset)
    """Permissions approved for this subject+scope combination."""

    issued_at: datetime | None = None
    """When this grant was issued."""

    expires_at: datetime | None = None
    """Optional expiry — ``None`` means no expiration."""

    metadata: Mapping[str, Any] = field(default_factory=dict)
    """Extensible bag for additional grant metadata."""

    def __hash__(self) -> int:
        return hash((self.subject_id, self.scope, self.permissions))
