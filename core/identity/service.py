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


class IdentityService(IdentityResolver):
    """Default identity resolver — Sprint 1 structural mapping only.

    Wraps raw identifiers into canonical identity objects without
    performing any authentication, token validation, or persistence.
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
