"""SecurityContext — tenant/workspace/resource-scope snapshot for a request."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SecurityContext:
    tenant_id: str = "default"
    workspace_id: Optional[str] = None
    owner_id: Optional[str] = None
    visibility: str = "private"
    resource_scope: Any = None
    tenant_resolution: Any = None
    authentication: Any = None
    authorization: Any = None
    scopes: frozenset = frozenset()

    def to_dict(self) -> dict:
        rs = self.resource_scope
        tr = self.tenant_resolution
        return {
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "owner_id": self.owner_id,
            "visibility": self.visibility,
            "resource_scope": rs.to_dict() if hasattr(rs, "to_dict") else rs,
            "tenant_resolution": tr.to_dict() if hasattr(tr, "to_dict") else tr,
            "scopes": sorted(self.scopes),
        }


__all__ = ["SecurityContext"]
