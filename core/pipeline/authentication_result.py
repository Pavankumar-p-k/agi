"""Authentication result model."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.identity.models import AuthenticationState, UserIdentity, SessionIdentity


@dataclass(frozen=True)
class AuthenticationResult:
    authenticated: bool = False
    state: AuthenticationState = AuthenticationState.ANONYMOUS
    principal: UserIdentity | None = None
    session: SessionIdentity | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def __hash__(self) -> int:
        return hash((self.authenticated, self.state, self.principal, self.session, self.reason, tuple(sorted(self.metadata.items()))))
