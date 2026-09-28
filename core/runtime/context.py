"""RuntimeContext — immutable runtime artifact bundle (Sprint 6)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class RuntimeContext:
    identity: Any = None
    authentication: Any = None
    authorization: Any = None
    tenant: Any = None
    resource_scope: Any = None
    resource_grant: Any = None
    activity_id: str = ""
    request_id: str = ""
    metadata: dict = field(default_factory=dict, compare=False)

    def to_dict(self) -> dict:
        def _ser(v: Any) -> Any:
            return v.to_dict() if hasattr(v, "to_dict") else v
        return {
            "identity": _ser(self.identity),
            "authentication": _ser(self.authentication),
            "authorization": _ser(self.authorization),
            "tenant": _ser(self.tenant),
            "resource_scope": _ser(self.resource_scope),
            "activity_id": self.activity_id,
            "request_id": self.request_id,
        }


__all__ = ["RuntimeContext"]
