"""ResourceGrant — an issued, tenant-scoped permission artifact."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class ResourceGrant:
    subject_id: str = ""
    scope: Any = None  # ResourceScope
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict, compare=False)

    def to_dict(self) -> dict:
        return {
            "subject_id": self.subject_id,
            "scope": self.scope.to_dict() if hasattr(self.scope, "to_dict") else None,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
        }


__all__ = ["ResourceGrant"]
