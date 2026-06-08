from __future__ import annotations

import fnmatch
import logging
from typing import Any, Dict, List, Optional, Set

from .schema import Role, Scope, AuthContext, Permission

logger = logging.getLogger("jarvis.core.authz.engine")

class PolicyEngine:
    """Evaluates access requests based on roles, scopes, and context."""

    def __init__(self):
        self._role_definitions: Dict[Role, Set[Scope]] = {}
        self._global_deny: Set[Scope] = set()
        
    def register_role(self, role: Role, scopes: Set[Scope]):
        self._role_definitions[role] = scopes
        logger.debug("[AuthZ] Registered role %s with %d scopes", role, len(scopes))

    def evaluate(self, ctx: AuthContext, required_scope: str, resource: Optional[str] = None) -> bool:
        """
        Main entry point for authorization checks.
        Evaluates if the context (user roles + direct scopes) covers the required scope.
        """
        # 1. Deny by default
        if not ctx:
            return False
            
        # 2. Admin escape hatch (if using strict RBAC, this might be a scope instead)
        if Role.ADMIN in ctx.roles:
            return True
            
        # 3. Resolve all effective scopes (roles -> scopes + direct scopes)
        effective_scopes = self._get_effective_scopes(ctx)
        
        # 4. Check for direct match or glob match (e.g. tools:execute:* covers tools:execute:high)
        for held_scope in effective_scopes:
            if self._scope_covers(held_scope, required_scope):
                logger.info("[AuthZ] Access GRANTED: user=%s scope=%s resource=%s (via %s)", 
                            ctx.user_id, required_scope, resource, held_scope)
                return True
                
        logger.warning("[AuthZ] Access DENIED: user=%s scope=%s resource=%s", 
                       ctx.user_id, required_scope, resource)
        return False

    def _get_effective_scopes(self, ctx: AuthContext) -> Set[str]:
        """Combine scopes from all roles and direct assignments."""
        scopes = set(str(s) for s in ctx.scopes)
        for role in ctx.roles:
            if role in self._role_definitions:
                scopes.update(str(s) for s in self._role_definitions[role])
        return scopes

    def _scope_covers(self, held_scope: str, required_scope: str) -> bool:
        """Check if one scope string covers another using fnmatch (glob)."""
        # Exact match
        if held_scope == required_scope:
            return True
            
        # Glob match (e.g. 'tools:execute:*' covers 'tools:execute:high')
        if "*" in held_scope:
            return fnmatch.fnmatch(required_scope, held_scope)
            
        return False

# Global singleton
authz_engine = PolicyEngine()
