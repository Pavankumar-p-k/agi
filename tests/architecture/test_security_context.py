"""Tests for SecurityContext — the read-only security state aggregate."""

from __future__ import annotations

import pytest

from core.identity.models import AuthenticationState, IdentityContext, UserIdentity
from core.identity.resource_scope import ResourceScope, Visibility
from core.pipeline.authentication_result import AuthenticationResult
from core.pipeline.authorization_result import AuthorizationResult
from core.pipeline.context import PipelineContext
from core.pipeline.resource_access_result import ResourceAccessResult
from core.pipeline.security_context import SecurityContext


class TestSecurityContextContract:
    """SecurityContext behaves like a frozen runtime artifact."""

    def test_frozen(self):
        sc = SecurityContext()
        with pytest.raises(Exception):
            sc.identity = IdentityContext()

    def test_defaults_all_none(self):
        sc = SecurityContext()
        assert sc.identity is None
        assert sc.authentication is None
        assert sc.authorization is None
        assert sc.resource_scope is None
        assert sc.resource_access is None

    def test_all_fields_populated(self):
        identity = IdentityContext(authentication_state=AuthenticationState.AUTHENTICATED)
        authn = AuthenticationResult(authenticated=True, state=AuthenticationState.AUTHENTICATED)
        authz = AuthorizationResult(allowed=True, scope="chat.execute")
        scope = ResourceScope(tenant_id="acme")
        ra = ResourceAccessResult(allowed=True, reason="ok", resource_scope=scope, requested_action="read", effective_visibility=Visibility.PUBLIC)
        sc = SecurityContext(identity=identity, authentication=authn, authorization=authz, resource_scope=scope, resource_access=ra)
        assert sc.identity is identity
        assert sc.authentication is authn
        assert sc.authorization is authz
        assert sc.resource_scope is scope
        assert sc.resource_access is ra

    def test_equality(self):
        sc1 = SecurityContext()
        sc2 = SecurityContext()
        assert sc1 == sc2

    def test_hashable(self):
        sc = SecurityContext()
        d = {sc: "value"}
        assert d[sc] == "value"


class TestPipelineContextSecurity:
    """PipelineContext.security aggregates identity, auth, and authz."""

    def test_security_all_none_by_default(self):
        ctx = PipelineContext(request_id="r1", transport="test")
        sc = ctx.security
        assert sc.identity is None
        assert sc.authentication is None
        assert sc.authorization is None
        assert sc.resource_scope is None
        assert sc.resource_access is None

    def test_security_reflects_identity(self):
        identity = IdentityContext(authentication_state=AuthenticationState.IDENTIFIED)
        ctx = PipelineContext(request_id="r2", transport="test")
        ctx.identity = identity
        sc = ctx.security
        assert sc.identity is identity
        assert sc.identity.authentication_state == AuthenticationState.IDENTIFIED
        assert sc.authentication is None
        assert sc.authorization is None
        assert sc.resource_scope is None
        assert sc.resource_access is None

    def test_security_reflects_all_five(self):
        identity = IdentityContext(authentication_state=AuthenticationState.AUTHENTICATED)
        authn = AuthenticationResult(authenticated=True, state=AuthenticationState.AUTHENTICATED)
        authz = AuthorizationResult(allowed=True, scope="chat.execute")
        scope = ResourceScope(tenant_id="acme")
        ra = ResourceAccessResult(allowed=True, reason="ok", resource_scope=scope, requested_action="read", effective_visibility=Visibility.PUBLIC)
        ctx = PipelineContext(request_id="r3", transport="test")
        ctx.identity = identity
        ctx.authentication_result = authn
        ctx.authorization_result = authz
        ctx.resource_scope = scope
        ctx.resource_access_result = ra
        sc = ctx.security
        assert sc.identity is identity
        assert sc.authentication is authn
        assert sc.authorization is authz
        assert sc.resource_scope is scope
        assert sc.resource_access is ra

    def test_security_readonly_snapshot(self):
        """Modifying context fields after accessing .security does not retroactively change it."""
        identity = IdentityContext(authentication_state=AuthenticationState.ANONYMOUS)
        ctx = PipelineContext(request_id="r4", transport="test")
        ctx.identity = identity
        sc_before = ctx.security
        ctx.authentication_result = AuthenticationResult(
            authenticated=False, state=AuthenticationState.ANONYMOUS,
        )
        assert sc_before.authentication is None
        assert ctx.security.authentication is not None

    def test_security_is_frozen(self):
        ctx = PipelineContext(request_id="r5", transport="test")
        sc = ctx.security
        with pytest.raises(Exception):
            sc.identity = IdentityContext()

    def test_security_not_stored_as_field(self):
        """security is a property, not a stored dataclass field."""
        ctx = PipelineContext(request_id="r6", transport="test")
        assert not hasattr(ctx, "_security")
        assert "security" not in ctx.__dataclass_fields__
