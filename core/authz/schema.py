from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


class Role(enum.StrEnum):
    ADMIN = "admin"            # Full system access
    OPERATOR = "operator"      # Management and high-risk tool execution
    DEVELOPER = "developer"    # Code, files, and standard tool access
    ANALYST = "analyst"        # Read-only access + reasoning tools
    GUEST = "guest"            # Minimal read access, no destructive tools


class Scope(enum.StrEnum):
    # --- Tool Execution ---
    TOOLS_EXECUTE_ALL = "tools:execute:*"
    TOOLS_EXECUTE_LOW = "tools:execute:low"      # safe search, status
    TOOLS_EXECUTE_MEDIUM = "tools:execute:medium" # browser, write_file
    TOOLS_EXECUTE_HIGH = "tools:execute:high"    # bash, python, delete_email
    
    # --- File System ---
    FILES_READ = "files:read"
    FILES_WRITE = "files:write"
    FILES_DELETE = "files:delete"
    FILES_ADMIN = "files:admin" # Manage root, external mounts
    
    # --- Memory ---
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_DELETE = "memory:delete"
    
    # --- System ---
    SYSTEM_STATUS = "system:status"
    SYSTEM_CONFIG = "system:config"
    SYSTEM_RESTART = "system:restart"
    SYSTEM_LOGS = "system:logs"
    
    # --- Governance ---
    GOVERNANCE_READ = "governance:read"
    GOVERNANCE_WRITE = "governance:write"
    
    # --- Plugins ---
    PLUGINS_LIST = "plugins:list"
    PLUGINS_MANAGE = "plugins:manage" # install/unload
    
    # --- Auth & Users ---
    AUTH_USERS_MANAGE = "auth:users:manage"
    AUTH_ROLES_MANAGE = "auth:roles:manage"

    # --- LLM & Failover ---
    LLM_COMPLETE = "llm:complete"
    LLM_FAILOVER_MANAGE = "llm:failover:manage"


@dataclass(frozen=True)
class Permission:
    scope: Scope
    constraints: Dict[str, Any] = field(default_factory=dict) # e.g. path matches, tool name in list


@dataclass
class AuthContext:
    user_id: str
    roles: Set[Role]
    scopes: Set[Scope]
    ip_address: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_admin(self) -> bool:
        return Role.ADMIN in self.roles
