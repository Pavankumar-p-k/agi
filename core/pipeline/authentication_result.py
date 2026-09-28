"""AuthenticationResult — output of the authentication stage (frozen artifact)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.identity.models import AuthenticationState, UserIdentity


@dataclass(frozen=True)
class SessionInfo:
    id: str = ""
    user_id: Optional[str] = None


@dataclass(frozen=True)
class AuthenticationResult:
    authenticated: bool = False
    state: AuthenticationState = AuthenticationState.ANONYMOUS
    reason: Optional[str] = None
    principal: Optional[UserIdentity] = None
    session: Optional[SessionInfo] = None
    user_id: Optional[str] = None
    # Excluded from eq/hash so results stay hashable (dict not hashable).
    metadata: dict = field(default_factory=dict, compare=False)


__all__ = ["AuthenticationResult", "SessionInfo"]
