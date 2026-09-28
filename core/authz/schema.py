"""Authorization vocabulary: roles, scopes, permissions, and auth context.

Pure data — no engine wiring lives here (see ``engine.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Role(str, Enum):
    """Principal roles recognised by the policy engine."""

    ADMIN = "admin"
    DEVELOPER = "developer"
    OPERATOR = "operator"
    ANALYST = "analyst"
    USER = "user"
    VIEWER = "viewer"
    GUEST = "guest"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return str(self.value)


class Scope(str, Enum):
    """Granular capability scopes. ``*`` / ``all`` / ``admin`` act as wildcards."""

    # Tool execution ladder
    TOOLS_EXECUTE_LOW = "tools:execute:low"
    TOOLS_EXECUTE_MEDIUM = "tools:execute:medium"
    TOOLS_EXECUTE_HIGH = "tools:execute:high"
    TOOLS_EXECUTE_ALL = "tools:execute:all"

    # Filesystem
    FILES_READ = "files:read"
    FILES_WRITE = "files:write"
    FILES_ADMIN = "files:admin"

    # Memory
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_ADMIN = "memory:admin"

    # Platform
    CHAT_EXECUTE = "chat.execute"
    RUNTIME_ADMIN = "runtime.admin"
    SYSTEM_ADMIN = "system:admin"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return str(self.value)


class Permission(str, Enum):
    """Coarse permission names surfaced to route/tool layers."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return str(self.value)


@dataclass
class AuthContext:
    """The authenticated principal plus its granted roles/scopes."""

    user_id: str = ""
    roles: set = field(default_factory=set)
    scopes: set = field(default_factory=set)
    session_id: Optional[str] = None
    is_authenticated: bool = True
    metadata: dict = field(default_factory=dict)

    def normalized_roles(self) -> set:
        """Roles as ``Role`` values (accepts raw strings)."""
        out = set()
        for role in self.roles or set():
            if isinstance(role, Role):
                out.add(role)
            else:
                try:
                    out.add(Role(str(role).lower()))
                except ValueError:
                    continue
        return out

    def normalized_scopes(self) -> set:
        """Scopes as plain scope strings (accepts ``Scope`` values)."""
        out = set()
        for scope in self.scopes or set():
            if isinstance(scope, Scope):
                out.add(str(scope.value))
            elif isinstance(scope, Permission):
                out.add(str(scope.value))
            else:
                out.add(str(scope))
        return out

    @property
    def is_admin(self) -> bool:
        return Role.ADMIN in self.normalized_roles()

    def has_role(self, role: Any) -> bool:
        try:
            return Role(str(role).lower()) in self.normalized_roles()
        except ValueError:
            return False

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "roles": sorted(str(r.value if isinstance(r, Role) else r)
                            for r in self.normalized_roles()),
            "scopes": sorted(self.normalized_scopes()),
            "session_id": self.session_id,
            "is_authenticated": self.is_authenticated,
        }


__all__ = ["Role", "Scope", "Permission", "AuthContext"]
