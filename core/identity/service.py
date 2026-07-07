from __future__ import annotations

from typing import Optional, Protocol

from core.identity.models import (
    AgentIdentity,
    AuthenticationState,
    IdentityContext,
    SessionIdentity,
    TenantIdentity,
    UserIdentity,
)


class IdentityResolver(Protocol):
    """Canonical identity resolution protocol.

    Implementations answer "who is this request?" without performing
    authorization decisions, token issuance, or persistence.
    """

    def create_context(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        agent_type: str | None = None,
        agent_version: str | None = None,
        agent_origin: str | None = None,
    ) -> IdentityContext:
        """Build an IdentityContext from raw request fields.

        Sprint 1: structural mapping only — no token validation,
        no DB lookups, no auth decisions.
        """
        ...

    def resolve_user(self, user_id: str) -> UserIdentity:
        """Resolve a user identifier to a UserIdentity."""
        ...

    def resolve_session(self, session_id: str) -> SessionIdentity:
        """Resolve a session identifier to a SessionIdentity."""
        ...

    def authenticate_session(
        self, token: str
    ) -> tuple[UserIdentity, SessionIdentity] | None:
        """Validate a session token against the authentication backend.

        Returns ``(user, session)`` if the token is valid, or ``None``
        if the token is invalid, expired, or the user was deleted.
        """
        ...

    def authorize(
        self,
        identity: IdentityContext,
        scope: str,
    ) -> AuthorizationResult:
        """Answer whether *identity* may perform *scope*.

        Never called by the pipeline directly — only by AuthorizationStage.
        """
        ...


class IdentityService(IdentityResolver):
    """Default identity resolver.

    Sprint 1: structural mapping only (create_context, resolve_user,
    resolve_session).

    Sprint 2: authenticate_session integrated with AuthManager for
    token validation.  IdentityService is the only adapter between
    the pipeline and the authentication backend.
    """

    def create_context(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        agent_type: str | None = None,
        agent_version: str | None = None,
        agent_origin: str | None = None,
    ) -> IdentityContext:
        user: UserIdentity | None = None
        session: SessionIdentity | None = None
        agent: AgentIdentity | None = None
        tenant = TenantIdentity()

        if user_id is not None:
            user = self.resolve_user(user_id)

        if session_id is not None:
            session = self.resolve_session(session_id)

        if agent_type is not None:
            agent = AgentIdentity(
                id=agent_type,
                type=agent_type,
                version=agent_version,
                origin=agent_origin,
            )

        if user is not None:
            auth_state = AuthenticationState.IDENTIFIED
        else:
            auth_state = AuthenticationState.ANONYMOUS

        return IdentityContext(
            user=user,
            session=session,
            agent=agent,
            tenant=tenant,
            authentication_state=auth_state,
        )

    def resolve_user(self, user_id: str) -> UserIdentity:
        """Sprint 1: wraps raw user_id into UserIdentity without validation."""
        return UserIdentity(id=user_id)

    def resolve_session(self, session_id: str) -> SessionIdentity:
        """Sprint 1: wraps raw session_id into SessionIdentity without validation."""
        return SessionIdentity(id=session_id)

    def authenticate_session(
        self, token: str
    ) -> tuple[UserIdentity, SessionIdentity] | None:
        """Validate *token* via AuthManager and return resolved identity.

        Returns ``None`` for invalid, expired, or deleted-user tokens.
        """
        from core.auth import get_auth_manager

        mgr = get_auth_manager()
        if not mgr.validate_token(token):
            return None
        username = mgr.get_username_for_token(token)
        if username is None:
            return None
        user = UserIdentity(id=username)
        session = SessionIdentity(id=token, user_id=username)
        return (user, session)

    def authorize(
        self,
        identity: IdentityContext,
        scope: str,
    ) -> AuthorizationResult:
        """Answer whether *identity* may perform *scope*.

        Delegates to PolicyEngine for the actual evaluation.
        Unauthenticated identities are always denied.
        """
        from core.pipeline.authorization_result import AuthorizationResult
        from core.auth import get_auth_manager
        from core.authz.engine import authz_engine
        from core.authz.schema import AuthContext, Role, Scope as AuthzScope

        if identity.user is None or identity.user.id is None:
            return AuthorizationResult(
                allowed=False,
                scope=scope,
                reason="no user identity",
            )

        user_id = identity.user.id
        mgr = get_auth_manager()

        roles: set[Role] = {Role.GUEST}
        scopes: set[AuthzScope] = set()

        if identity.authentication_state in (
            AuthenticationState.AUTHENTICATED,
            AuthenticationState.SYSTEM,
        ):
            resolved = mgr.resolve_context(user_id)
            roles = resolved.roles
            scopes = resolved.scopes

        ctx = AuthContext(
            user_id=user_id,
            roles=roles,
            scopes=scopes,
        )

        allowed = authz_engine.evaluate(ctx, scope)
        return AuthorizationResult(
            allowed=allowed,
            scope=scope,
            permissions=frozenset(str(s) for s in scopes),
            roles=frozenset(r.value for r in roles),
            reason=None if allowed else f"missing scope: {scope}",
        )
