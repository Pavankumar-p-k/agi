from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class AuthorizationResult:
    """Typed result of the AuthorizationStage.

    Created once by AuthorizationStage and never mutated.  Records whether
    the request's authenticated identity is permitted to perform the
    requested scope.

    Only ``AuthorizationStage`` may construct this dataclass.
    """

    allowed: bool
    """``True`` when the caller is permitted to perform the requested scope."""

    scope: str
    """The canonical scope that was evaluated (e.g. ``"chat.execute"``)."""

    permissions: frozenset[str] = field(default_factory=frozenset)
    """Effective permissions granted to this identity for the evaluated scope."""

    roles: frozenset[str] = field(default_factory=frozenset)
    """Roles resolved for this identity (e.g. ``{"admin", "developer"}``)."""

    reason: str | None = None
    """Human-readable explanation (e.g. ``"admin override"``, ``"missing scope"``)."""

    metadata: Mapping[str, Any] = field(default_factory=dict)
    """Extensible bag for additional authorization details."""

    def __hash__(self) -> int:
        return hash((self.allowed, self.scope))
