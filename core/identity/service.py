"""IdentityService — authenticate sessions + authorize scopes.

Contract (tests/architecture/test_authentication.py,
tests/architecture/test_authorization.py):
- ``authenticate_session(token)`` returns ``(UserIdentity, SessionIdentity)``
  or None;
- ``authorize(identity, scope)`` returns a frozen AuthorizationResult with
  scope-table validation, SYSTEM shortcut, and admin-role gating.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional, Tuple

from core.identity.models import AuthenticationState
from core.pipeline.authorization_result import AuthorizationResult

# Scopes the pipeline knows about; anything else is rejected explicitly.
KNOWN_SCOPES = (
    "chat.execute",
    "memory.read",
    "memory.write",
    "admin.runtime",
    "settings.write",
    "runtime.admin",
)

# Scopes that require the admin role.
_ADMIN_SCOPES = ("admin.", "runtime.admin", "settings.write")


class IdentityService:
    """Session authentication + scope authorization over AuthManager."""

    def __init__(self, **kwargs: Any):
        self._tenant_resolver = None
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "_tenant_resolver") or self._tenant_resolver is None:
            from core.identity.tenant_resolver import DefaultTenantResolver
            self._tenant_resolver = DefaultTenantResolver()

    # ── context construction ─────────────────────────────────────────
    def create_context(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_version: str = "",
        agent_origin: str = "",
    ):
        """Build an IdentityContext from raw request attributes."""
        from core.identity.models import (
            AgentIdentity, AuthenticationState, IdentityContext,
            SessionIdentity, UserIdentity,
        )
        user = UserIdentity(id=user_id) if user_id else None
        agent = AgentIdentity(id=agent_type or "", type=agent_type or "agent",
                              version=agent_version, origin=agent_origin) \
            if agent_type else None
        session = SessionIdentity(id=session_id, user_id=user_id) \
            if session_id else None
        state = AuthenticationState.IDENTIFIED if user_id \
            else AuthenticationState.ANONYMOUS
        return IdentityContext(
            user=user, agent=agent, session=session,
            authentication_state=state,
        )

    def resolve_user(self, user_id: str):
        from core.identity.models import UserIdentity
        return UserIdentity(id=user_id)

    def resolve_session(self, session_id: str):
        from core.identity.models import SessionIdentity
        return SessionIdentity(id=session_id)

    def resolve_tenant(self, identity: Any):
        """Delegate to the tenant resolver (overridable via _tenant_resolver)."""
        return self._tenant_resolver.resolve_tenant(identity)

    def uuid4(self) -> str:
        return uuid.uuid4().hex

    # ── authentication ───────────────────────────────────────────────
    def authenticate_session(
        self, token: str,
    ) -> Optional[Tuple[Any, Any]]:
        """Validate a session token; returns (user, session) or None."""
        if not token:
            return None
        try:
            from core.auth import get_auth_manager
            from core.identity.models import SessionIdentity, UserIdentity

            am = get_auth_manager()
            username = am.get_username_for_token(token)
            if not username:
                return None
            user = UserIdentity(id=username, username=username,
                                roles=am.roles(username))
            session = SessionIdentity(id=token, user_id=username)
            return user, session
        except Exception:  # noqa: BLE001 — auth backend unavailable
            return None

    # ── authorization ────────────────────────────────────────────────
    def authorize(self, identity: Any, scope: str) -> AuthorizationResult:
        user = getattr(identity, "user", None)

        # Unknown scopes are rejected before identity checks.
        if scope and scope not in KNOWN_SCOPES:
            return AuthorizationResult(allowed=False,
                                       reason=f"unknown scope: {scope}",
                                       scope=scope)

        if user is None or not getattr(user, "id", ""):
            return AuthorizationResult(allowed=False, reason="no user identity",
                                       scope=scope)

        state = getattr(identity, "authentication_state", None)
        state_val = getattr(state, "value", state)

        # SYSTEM identities are always allowed (scheduler/internal calls).
        if state_val == AuthenticationState.SYSTEM.value:
            roles = list(getattr(user, "roles", []) or []) or ["admin"]
            return AuthorizationResult(
                allowed=True, reason="system identity", scope=scope,
                roles=frozenset(roles),
                permissions=frozenset({scope} if scope else ()),
            )

        if state_val != AuthenticationState.AUTHENTICATED.value:
            return AuthorizationResult(allowed=False, reason="not authenticated",
                                       scope=scope)

        # Roles: take the live view from the AuthManager when the user exists
        # there (fixtures mutate admin flags after token creation).
        roles = list(getattr(user, "roles", []) or [])
        try:
            from core.auth import get_auth_manager
            am = get_auth_manager()
            username = getattr(user, "username", "") or getattr(user, "id", "")
            if am.users.get(username):
                roles = am.roles(username)
        except Exception:  # noqa: BLE001 — auth backend optional for authorize
            pass

        if any(scope.startswith(prefix) for prefix in _ADMIN_SCOPES) \
                and "admin" not in roles:
            return AuthorizationResult(allowed=False,
                                       reason="admin role required", scope=scope)

        return AuthorizationResult(
            allowed=True, reason="authorized", scope=scope,
            roles=frozenset(roles),
            permissions=frozenset({scope} if scope else ()),
        )


class IdentityResolver:
    """Resolves IdentityContext objects from raw request attributes."""

    def resolve(self, user_id: Optional[str] = None, **kwargs: Any):
        from core.identity.models import (
            AuthenticationState, IdentityContext, UserIdentity,
        )
        if user_id:
            return IdentityContext(
                user=UserIdentity(id=user_id),
                authentication_state=AuthenticationState.IDENTIFIED,
            )
        return IdentityContext()


_identity_service: Optional[IdentityService] = None


def get_identity_service() -> IdentityService:
    global _identity_service
    if _identity_service is None:
        _identity_service = IdentityService()
    return _identity_service


def set_identity_service(service: IdentityService) -> None:
    global _identity_service
    _identity_service = service


__all__ = [
    "IdentityService", "IdentityResolver", "AuthorizationResult",
    "get_identity_service", "KNOWN_SCOPES",
]
