"""Outcome — terminal runtime artifact of one Activity (Sprint 5.5C contract)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from core.pipeline.observation import Observation


@dataclass(frozen=True)
class Outcome:
    """Immutable summary of one activity execution (Rule 30 scope carrier)."""

    activity_id: str = ""
    success: bool = False
    observations: List[Observation] = field(default_factory=list)
    status: str = ""
    error: Optional[str] = None
    resource_scope: Any = None
    metrics: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "success": self.success,
            "status": self.status,
            "error": self.error,
            "resource_scope": (
                self.resource_scope.to_dict()
                if hasattr(self.resource_scope, "to_dict")
                else self.resource_scope
            ),
            "observations": [o.to_dict() for o in self.observations],
            "metrics": dict(self.metrics),
        }


__all__ = ["Outcome"]
