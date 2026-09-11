from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    OPERATOR = "operator"
    ANALYST = "analyst"


class Scope(str, Enum):
    TOOLS_EXECUTE_LOW = "tools:execute:low"
    TOOLS_EXECUTE_MEDIUM = "tools:execute:medium"
    TOOLS_EXECUTE_HIGH = "tools:execute:high"
    TOOLS_EXECUTE_ALL = "tools:execute:*"
    FILES_READ = "files:read"
    FILES_ADMIN = "files:admin"


class Permission(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class AuthContext:
    user_id: str
    roles: set[Role] = field(default_factory=set)
    scopes: set[str] = field(default_factory=set)
