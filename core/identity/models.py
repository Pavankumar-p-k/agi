"""Identity model definitions compatible with the architecture tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AuthenticationState(str, Enum):
    ANONYMOUS = "anonymous"
    IDENTIFIED = "identified"
    AUTHENTICATED = "authenticated"
    SYSTEM = "system"


@dataclass
class UserIdentity:
    id: str | None = None
    username: str | None = None
    email: str | None = None
    roles: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.roles is None:
            self.roles = ()
        self.roles = tuple(self.roles)
        self.metadata = dict(self.metadata or {})


@dataclass
class SessionIdentity:
    id: str = ""
    user_id: str = ""
    token: str | None = None
    expiry: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.metadata = dict(self.metadata or {})


@dataclass
class TenantIdentity:
    id: str = "default"
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.metadata = dict(self.metadata or {})


@dataclass
class AgentIdentity:
    id: str | None = None
    type: str = "agent"
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.metadata = dict(self.metadata or {})


@dataclass
class IdentityContext:
    user: UserIdentity | None = None
    agent: AgentIdentity | None = None
    session: SessionIdentity | None = None
    tenant: TenantIdentity | None = None
    authentication_state: AuthenticationState = AuthenticationState.ANONYMOUS
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.metadata = dict(self.metadata or {})
        if self.user is not None and self.user.id is None:
            self.user.id = self.user.username or ""
        if self.tenant is None:
            self.tenant = TenantIdentity(id="default")
