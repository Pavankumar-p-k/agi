"""Authorization result model."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool = False
    scope: str = ""
    reason: str | None = None
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "roles", frozenset(self.roles or ()))
        object.__setattr__(self, "permissions", frozenset(self.permissions or ()))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def __hash__(self) -> int:
        return hash((self.allowed, self.scope, self.reason, tuple(sorted(self.roles)), tuple(sorted(self.permissions)), tuple(sorted(self.metadata.items()))))
