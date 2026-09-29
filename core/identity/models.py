"""Identity domain models.

Sub-identities (user/agent/session/tenant) are immutable value snapshots.
``IdentityContext`` is deliberately *not* frozen: the AuthenticationStage owns
the ANONYMOUS → IDENTIFIED → AUTHENTICATED transition and rewrites the context
in place (architecture Rule 14), while still needing to be usable as a
dictionary key (trace validation), hence ``unsafe_hash``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class AuthenticationState(str, Enum):
    """Verification level of the request's principal."""

    ANONYMOUS = "anonymous"
    IDENTIFIED = "identified"
    AUTHENTICATED = "authenticated"
    FAILED = "failed"
    SYSTEM = "system"


@dataclass(frozen=True)
class UserIdentity:
    """A human (or service) principal."""

    id: str = ""
    username: str = ""
    email: Optional[str] = None
    display_name: Optional[str] = None
    roles: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.roles, tuple):
            object.__setattr__(self, "roles", tuple(self.roles or ()))

    @property
    def role_set(self) -> frozenset[str]:
        return frozenset(self.roles or ())


@dataclass(frozen=True)
class AgentIdentity:
    """The software agent acting on the principal's behalf."""

    id: str = ""
    type: str = "agent"
    version: Optional[str] = None
    origin: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class SessionIdentity:
    """A validated session binding a principal to a token."""

    id: str = ""
    user_id: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class TenantIdentity:
    """The tenant partition claimed by the request.

    ``id`` is ``None`` when the identity carries no explicit tenant; the
    resolver turns that into the default-tenant sentinel.
    """

    id: Optional[str] = None
    organization_id: Optional[str] = None
    workspace_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass(unsafe_hash=True)
class IdentityContext:
    """Full identity snapshot attached to a request."""

    user: Optional[UserIdentity] = None
    agent: Optional[AgentIdentity] = None
    session: Optional[SessionIdentity] = None
    tenant: TenantIdentity = field(default_factory=TenantIdentity)
    authentication_state: AuthenticationState = AuthenticationState.ANONYMOUS
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)


__all__ = [
    "AgentIdentity",
    "AuthenticationState",
    "IdentityContext",
    "SessionIdentity",
    "TenantIdentity",
    "UserIdentity",
]
