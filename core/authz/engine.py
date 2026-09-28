"""Role/permission policy engine.

Evaluates an :class:`AuthContext` against a requested scope using the
role→scope grants registered on the engine. Wildcards:

``tools:execute:*`` / ``tools:execute:all`` / ``tools:execute:admin``
all cover every scope underneath ``tools:execute:``.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from core.authz.schema import AuthContext, Role, Scope

_WILDCARD_SUFFIXES = (":*", ":all", ":admin")


class PolicyEngine:
    """In-memory role→scope grants with wildcard-aware evaluation."""

    def __init__(self) -> None:
        self._role_scopes: dict[str, set[str]] = {}
        # Admin is never locked out of anything.
        self.register_role(Role.ADMIN, {"*"})

    # ── registration ────────────────────────────────────────────────
    @staticmethod
    def _role_key(role: Any) -> str:
        if isinstance(role, Role):
            return role.value
        return str(role).lower()

    @staticmethod
    def _scope_str(scope: Any) -> str:
        if isinstance(scope, Scope):
            return str(scope.value)
        return str(scope)

    def register_role(self, role: Any, scopes: Iterable[Any]) -> None:
        """Grant *scopes* to *role* (additive)."""
        key = self._role_key(role)
        grants = self._role_scopes.setdefault(key, set())
        for scope in scopes or ():
            grants.add(self._scope_str(scope))

    def unregister_role(self, role: Any) -> None:
        self._role_scopes.pop(self._role_key(role), None)

    def scopes_for(self, role: Any) -> set:
        return set(self._role_scopes.get(self._role_key(role), set()))

    def roles(self) -> list:
        return sorted(self._role_scopes)

    def clear(self) -> None:
        self._role_scopes.clear()

    # ── evaluation ──────────────────────────────────────────────────
    def _scope_covers(self, granted: Any, required: Any) -> bool:
        """True when *granted* is at least as broad as *required*."""
        granted_s = self._scope_str(granted)
        required_s = self._scope_str(required)
        if granted_s == "*" or granted_s == required_s:
            return True
        for suffix in _WILDCARD_SUFFIXES:
            if granted_s.endswith(suffix):
                prefix = granted_s[: -len(suffix)]
                if required_s == prefix or required_s.startswith(prefix + ":"):
                    return True
        return False

    def evaluate(self, context: Optional[AuthContext], scope: Any) -> bool:
        """True when *context* may exercise *scope*."""
        if context is None:
            return False
        required = self._scope_str(scope)
        roles = context.normalized_roles() if isinstance(context, AuthContext) \
            else set()
        if Role.ADMIN in roles:
            return True

        # Direct grants on the context itself.
        for granted in (context.normalized_scopes()
                        if isinstance(context, AuthContext) else set()):
            if self._scope_covers(granted, required):
                return True

        # Role-derived grants.
        for role in roles:
            for granted in self._role_scopes.get(role.value, set()):
                if self._scope_covers(granted, required):
                    return True
        return False

    def evaluate_any(self, context: Optional[AuthContext], scopes: Iterable[Any]) -> bool:
        return any(self.evaluate(context, s) for s in (scopes or ()))

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"PolicyEngine(roles={self.roles()})"


# Module-level singleton used by tool dispatch and identity services.
authz_engine = PolicyEngine()

# Sensible built-in grants for the default deployment.
authz_engine.register_role(Role.OPERATOR, {
    Scope.TOOLS_EXECUTE_ALL.value,
    Scope.FILES_READ.value,
    Scope.MEMORY_READ.value,
    Scope.MEMORY_WRITE.value,
})
authz_engine.register_role(Role.DEVELOPER, {
    Scope.TOOLS_EXECUTE_MEDIUM.value,
    Scope.FILES_READ.value,
    Scope.FILES_WRITE.value,
    Scope.MEMORY_READ.value,
    Scope.MEMORY_WRITE.value,
})
authz_engine.register_role(Role.ANALYST, {
    Scope.MEMORY_READ.value,
    Scope.TOOLS_EXECUTE_LOW.value,
})
authz_engine.register_role(Role.USER, {Scope.CHAT_EXECUTE.value})
authz_engine.register_role(Role.VIEWER, {})
authz_engine.register_role(Role.GUEST, {})


def get_policy_engine() -> PolicyEngine:
    """Return the process-wide policy engine."""
    return authz_engine


def set_policy_engine(engine: PolicyEngine) -> None:
    """Swap the process-wide policy engine (tests/deployments)."""
    global authz_engine
    authz_engine = engine


__all__ = ["PolicyEngine", "authz_engine", "get_policy_engine", "set_policy_engine"]
