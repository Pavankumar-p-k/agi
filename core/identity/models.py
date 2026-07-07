from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AuthenticationState(Enum):
    ANONYMOUS = "anonymous"
    IDENTIFIED = "identified"
    AUTHENTICATED = "authenticated"
    SYSTEM = "system"


@dataclass(frozen=True)
class UserIdentity:
    id: str
    email: str | None = None
    display_name: str | None = None
    roles: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentIdentity:
    id: str
    type: str
    version: str | None = None
    origin: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionIdentity:
    id: str
    user_id: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TenantIdentity:
    id: str | None = None
    organization_id: str | None = None
    workspace_id: str | None = None


@dataclass(frozen=True)
class IdentityContext:
    user: UserIdentity | None = None
    session: SessionIdentity | None = None
    agent: AgentIdentity | None = None
    tenant: TenantIdentity = field(default_factory=TenantIdentity)
    authentication_state: AuthenticationState = AuthenticationState.ANONYMOUS
