"""ResourceAccessResult — the ResourceAccessStage's decision artifact.

Constructed only by ``core.pipeline.stages.resource_access`` (architecture
Rule 20). Frozen and hashable so a decision can be compared verbatim during
replay validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ResourceAccessResult:
    """Outcome of one visibility/ownership access check."""

    allowed: bool
    reason: str = ""
    resource_scope: Any = None
    requested_action: str = "read"
    effective_visibility: Any = None
    metadata: dict = field(default_factory=dict, compare=False)

    def to_dict(self) -> dict:
        scope = self.resource_scope
        visibility = self.effective_visibility
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "requested_action": self.requested_action,
            "effective_visibility": getattr(visibility, "value", visibility),
            "resource_scope": (
                scope.to_dict() if hasattr(scope, "to_dict") else scope
            ),
        }


__all__ = ["ResourceAccessResult"]
