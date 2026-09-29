"""ResourceGrant — an issued, tenant-scoped permission artifact.

Issued by AuthorizationStage (only) when a requested scope is authorized,
consumed by ResourceAccessStage (expiry decision) and the execution layer
(what the run is allowed to touch). Frozen and hashable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class ResourceGrant:
    """A time-bounded permission over one resource scope."""

    subject_id: str = ""
    scope: Any = None  # ResourceScope
    permissions: frozenset = frozenset()
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict, compare=False)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """True when ``expires_at`` has passed (grants without expiry never do)."""
        expires = self.expires_at
        if expires is None:
            return False
        moment = now or datetime.now(timezone.utc)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return expires < moment

    def allows(self, permission: str) -> bool:
        return not self.permissions or permission in self.permissions

    def to_dict(self) -> dict:
        return {
            "subject_id": self.subject_id,
            "scope": self.scope.to_dict() if hasattr(self.scope, "to_dict") else None,
            "permissions": sorted(self.permissions),
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


__all__ = ["ResourceGrant"]
