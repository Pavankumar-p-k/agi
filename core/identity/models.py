"""Identity domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AuthenticationState(str, Enum):
    ANONYMOUS = "ANONYMOUS"
    IDENTIFIED = "IDENTIFIED"
    AUTHENTICATED = "AUTHENTICATED"
    FAILED = "FAILED"
    SYSTEM = "SYSTEM"


@dataclass
class UserIdentity:
    id: str = ""
    username: str = ""
    email: Optional[str] = None
    roles: list[str] = field(default_factory=list)


@dataclass
class AgentIdentity:
    id: str = ""
    type: str = "agent"
    version: str = ""
    origin: str = ""
    owner: Optional[str] = None


@dataclass
class SessionIdentity:
    id: str = ""
    user_id: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class TenantIdentity:
    id: str = "default"
    organization_id: Optional[str] = None
    workspace_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IdentityContext:
    """Full identity snapshot attached to a request."""
    user: Optional[UserIdentity] = None
    agent: Optional[AgentIdentity] = None
    session: Optional[SessionIdentity] = None
    tenant: Optional[TenantIdentity] = None
    authentication_state: AuthenticationState = AuthenticationState.ANONYMOUS
    metadata: dict[str, Any] = field(default_factory=dict)
