"""Tests for IdentityService — structural mapping only, no auth."""

from __future__ import annotations

from core.identity import (
    IdentityService,
    get_identity_service,
    set_identity_service,
)
from core.identity.models import (
    AgentIdentity,
    AuthenticationState,
    IdentityContext,
    SessionIdentity,
    UserIdentity,
)


def test_create_context_anonymous():
    svc = IdentityService()
    ctx = svc.create_context()
    assert isinstance(ctx, IdentityContext)
    assert ctx.user is None
    assert ctx.session is None
    assert ctx.authentication_state == AuthenticationState.ANONYMOUS


def test_create_context_identified():
    svc = IdentityService()
    ctx = svc.create_context(user_id="user-1", session_id="sess-1")
    assert ctx.user is not None
    assert ctx.user.id == "user-1"
    assert ctx.session is not None
    assert ctx.session.id == "sess-1"
    assert ctx.authentication_state == AuthenticationState.IDENTIFIED


def test_create_context_with_agent():
    svc = IdentityService()
    ctx = svc.create_context(
        agent_type="web",
        agent_version="1.0",
        agent_origin="browser",
    )
    assert ctx.agent is not None
    assert ctx.agent.type == "web"
    assert ctx.agent.version == "1.0"
    assert ctx.agent.origin == "browser"


def test_create_context_anonymous_with_agent():
    svc = IdentityService()
    ctx = svc.create_context(agent_type="scheduler")
    assert ctx.authentication_state == AuthenticationState.ANONYMOUS
    assert ctx.agent is not None
    assert ctx.agent.type == "scheduler"


def test_resolve_user_roundtrip():
    svc = IdentityService()
    user = svc.resolve_user("user-1")
    assert isinstance(user, UserIdentity)
    assert user.id == "user-1"
    assert user.email is None


def test_resolve_session_roundtrip():
    svc = IdentityService()
    session = svc.resolve_session("sess-1")
    assert isinstance(session, SessionIdentity)
    assert session.id == "sess-1"


def test_get_identity_service_singleton():
    svc1 = get_identity_service()
    svc2 = get_identity_service()
    assert svc1 is svc2


def test_set_identity_service_override():
    original = get_identity_service()
    fake = IdentityService()
    set_identity_service(fake)
    assert get_identity_service() is fake
    set_identity_service(original)
    assert get_identity_service() is original


def test_create_context_no_mutation():
    svc = IdentityService()
    ctx = svc.create_context(user_id="user-1")
    assert ctx.authentication_state == AuthenticationState.IDENTIFIED
