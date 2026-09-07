"""Identity resolution and authentication helpers."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from core import auth as auth_module
from core.identity.models import AuthenticationState, IdentityContext, SessionIdentity, TenantIdentity, UserIdentity


@dataclass
class IdentityResolver:
    default_tenant_id: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolve(self, user: UserIdentity | None = None, session: SessionIdentity | None = None, tenant: TenantIdentity | None = None) -> IdentityContext:
        if user is None:
            user = UserIdentity(id="", username="", email="")
        if session is None:
            session = SessionIdentity(id="", user_id=str(user.id or user.username or ""))
        if tenant is None:
            tenant = TenantIdentity(id=self.default_tenant_id)
        return IdentityContext(user=user, session=session, tenant=tenant, metadata=dict(self.metadata))


_IDENTITY_SERVICE: "IdentityService | None" = None


@dataclass
class IdentityService:
    resolver: IdentityResolver = field(default_factory=IdentityResolver)

    def resolve_identity(self, user: UserIdentity | None = None, session: SessionIdentity | None = None, tenant: TenantIdentity | None = None) -> IdentityContext:
        return self.resolver.resolve(user=user, session=session, tenant=tenant)

    def authenticate_session(self, token: str | None) -> tuple[UserIdentity, SessionIdentity] | None:
        if not token:
            return None
        manager = auth_module.get_auth_manager()
        session_data = manager.sessions.get(token)
        if not isinstance(session_data, dict):
            return None
        if session_data.get("expiry") is not None and time.time() > float(session_data["expiry"]):
            return None
        user_id = str(session_data.get("user_id") or session_data.get("username") or "")
        user = manager.users.get(user_id)
        if user is None:
            return None
        session = SessionIdentity(id=token, user_id=user_id, token=token, expiry=session_data.get("expiry"), metadata={})
        principal = UserIdentity(id=user_id, username=user_id, roles=tuple(user.get("roles", [])), metadata=dict(user))
        return principal, session

    def authorize(self, identity: IdentityContext | None, scope: str) -> Any:
        from core.pipeline.authorization_result import AuthorizationResult

        if identity is None:
            return AuthorizationResult(allowed=False, scope=scope, reason="no user identity")

        user = getattr(identity, "user", None)
        if identity.authentication_state == AuthenticationState.SYSTEM:
            if user is None or not getattr(user, "id", None):
                return AuthorizationResult(allowed=False, scope=scope, reason="no user identity")
            return AuthorizationResult(allowed=True, scope=scope, roles=frozenset(getattr(user, "roles", ()) or ()), reason="system identity")

        if user is None or not getattr(user, "id", None):
            if scope == "":
                return AuthorizationResult(allowed=False, scope="", reason="no scope requested")
            return AuthorizationResult(allowed=False, scope=scope, roles=frozenset(), permissions=frozenset(), reason="no user identity")

        manager = auth_module.get_auth_manager()
        user_record = manager.users.get(str(user.id), {}) if manager else {}
        roles = set(user_record.get("roles", []))
        if user_record.get("is_admin"):
            roles.add("admin")
        permissions = set(user_record.get("permissions", []))
        if user_record.get("is_admin") or "admin" in roles:
            return AuthorizationResult(allowed=True, scope=scope, roles=frozenset(roles), permissions=frozenset(permissions), reason=None)
        if scope in permissions:
            return AuthorizationResult(allowed=True, scope=scope, roles=frozenset(roles), permissions=frozenset(permissions), reason=None)
        if scope == "chat.execute":
            return AuthorizationResult(allowed=True, scope=scope, roles=frozenset(roles), permissions=frozenset(permissions | {scope}), reason=None)
        if scope == "":
            return AuthorizationResult(allowed=False, scope="", reason="no scope requested")
        return AuthorizationResult(allowed=False, scope=scope, roles=frozenset(roles), permissions=frozenset(permissions), reason=f"unknown scope: {scope}")


def get_identity_service() -> IdentityService:
    global _IDENTITY_SERVICE
    if _IDENTITY_SERVICE is None:
        _IDENTITY_SERVICE = IdentityService()
    return _IDENTITY_SERVICE


def set_identity_service(service: IdentityService | None) -> IdentityService | None:
    """Replace the process-wide identity service, primarily for composition/tests."""
    global _IDENTITY_SERVICE
    previous = _IDENTITY_SERVICE
    _IDENTITY_SERVICE = service
    return previous
