"""Tests for identity dataclasses — frozen, equality, defaults."""

from __future__ import annotations

from datetime import datetime, timezone

from core.identity.models import (
    AgentIdentity,
    AuthenticationState,
    IdentityContext,
    SessionIdentity,
    TenantIdentity,
    UserIdentity,
)


def test_user_identity_frozen():
    u = UserIdentity(id="user-1")
    try:
        u.id = "other"
        assert False, "should be frozen"
    except Exception:
        pass


def test_user_identity_defaults():
    u = UserIdentity(id="user-1")
    assert u.email is None
    assert u.display_name is None
    assert u.roles == ()
    assert u.metadata == {}


def test_identity_context_defaults_anonymous():
    ctx = IdentityContext()
    assert ctx.user is None
    assert ctx.session is None
    assert ctx.agent is None
    assert ctx.tenant.id is None
    assert ctx.authentication_state == AuthenticationState.ANONYMOUS


def test_identity_context_with_user():
    user = UserIdentity(id="user-1", email="a@b.com")
    ctx = IdentityContext(user=user, authentication_state=AuthenticationState.IDENTIFIED)
    assert ctx.user is not None
    assert ctx.user.id == "user-1"
    assert ctx.user.email == "a@b.com"
    assert ctx.authentication_state == AuthenticationState.IDENTIFIED


def test_agent_identity_defaults():
    a = AgentIdentity(id="cli", type="cli")
    assert a.version is None
    assert a.origin is None
    assert a.metadata == {}


def test_agent_identity_full():
    a = AgentIdentity(
        id="web-1",
        type="web",
        version="1.0",
        origin="browser",
        metadata={"user_agent": "Chrome"},
    )
    assert a.type == "web"
    assert a.version == "1.0"
    assert a.origin == "browser"


def test_session_identity_defaults():
    s = SessionIdentity(id="sess-1")
    assert s.user_id is None
    assert s.created_at is None
    assert s.expires_at is None


def test_session_identity_full():
    now = datetime.now(timezone.utc)
    s = SessionIdentity(id="sess-1", user_id="user-1", created_at=now)
    assert s.user_id == "user-1"
    assert s.created_at == now


def test_tenant_identity_defaults():
    t = TenantIdentity()
    assert t.id is None
    assert t.organization_id is None
    assert t.workspace_id is None


def test_tenant_identity_full():
    t = TenantIdentity(id="tenant-1", organization_id="org-1", workspace_id="ws-1")
    assert t.id == "tenant-1"
    assert t.organization_id == "org-1"
    assert t.workspace_id == "ws-1"


def test_identity_context_equality():
    ctx1 = IdentityContext(authentication_state=AuthenticationState.ANONYMOUS)
    ctx2 = IdentityContext(authentication_state=AuthenticationState.ANONYMOUS)
    assert ctx1 == ctx2


def test_identity_context_hashable():
    ctx = IdentityContext(authentication_state=AuthenticationState.SYSTEM)
    d = {ctx: "value"}
    assert d[ctx] == "value"


def test_authentication_state_enum_values():
    assert AuthenticationState.ANONYMOUS.value == "anonymous"
    assert AuthenticationState.IDENTIFIED.value == "identified"
    assert AuthenticationState.AUTHENTICATED.value == "authenticated"
    assert AuthenticationState.SYSTEM.value == "system"
