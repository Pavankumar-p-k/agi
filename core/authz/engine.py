from __future__ import annotations

from core.authz.schema import AuthContext, Role


class PolicyEngine:
    def __init__(self) -> None:
        self.roles: dict[Role, set[str]] = {}

    def register_role(self, role: Role, scopes: set[str]) -> None:
        self.roles[role] = {str(scope.value if hasattr(scope, "value") else scope) for scope in scopes}

    def _scope_covers(self, granted: str, requested: str) -> bool:
        if granted == requested:
            return True
        if granted.endswith(":*"):
            return requested.startswith(granted[:-1])
        return False

    def evaluate(self, context: AuthContext, requested: str) -> bool:
        requested = str(requested.value if hasattr(requested, "value") else requested)
        if Role.ADMIN in context.roles:
            return True
        granted = set(context.scopes)
        for role in context.roles:
            granted.update(self.roles.get(role, set()))
        return any(self._scope_covers(scope, requested) for scope in granted)


authz_engine = PolicyEngine()
