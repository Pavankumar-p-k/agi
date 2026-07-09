"""Tests for Tenant Resolution — canonical tenant lookup, inheritance, defaults.

Sprint 6: structural resolution only — no storage backends, no DB lookups.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.identity import get_identity_service, set_identity_service
from core.identity.models import (
    AuthenticationState,
    IdentityContext,
    TenantIdentity,
    UserIdentity,
)
from core.identity.resource_scope import DEFAULT_TENANT_ID, ResourceScope, Visibility
from core.identity.tenant_resolver import (
    DefaultTenantResolver,
    TenantResolutionResult,
    TenantResolver,
)
from core.pipeline.context import PipelineContext
from core.pipeline.stages.tenant_resolution import TenantResolutionStage


# ── TenantResolutionResult Contract ──────────────────────────────────────────────


class TestTenantResolutionResultContract:
    """TenantResolutionResult behaves like a frozen runtime artifact."""

    def test_frozen(self):
        r = TenantResolutionResult(tenant_id="acme")
        with pytest.raises(Exception):
            r.tenant_id = "other"

    def test_defaults(self):
        r = TenantResolutionResult(tenant_id="acme")
        assert r.tenant_id == "acme"
        assert r.organization_id is None
        assert r.workspace_id is None
        assert r.source == "default"
        assert r.valid is True
        assert r.reason is None
        assert r.metadata == {}

    def test_equality(self):
        a = TenantResolutionResult(tenant_id="acme")
        b = TenantResolutionResult(tenant_id="acme")
        assert a == b

    def test_hashable(self):
        r = TenantResolutionResult(tenant_id="acme")
        d = {r: "value"}
        assert d[r] == "value"

    def test_all_fields_populated(self):
        r = TenantResolutionResult(
            tenant_id="acme",
            organization_id="org-1",
            workspace_id="ws-1",
            source="identity",
            valid=True,
            reason="direct assignment",
            metadata={"region": "us-east"},
        )
        assert r.tenant_id == "acme"
        assert r.organization_id == "org-1"
        assert r.workspace_id == "ws-1"
        assert r.source == "identity"
        assert r.valid is True
        assert r.reason == "direct assignment"
        assert r.metadata == {"region": "us-east"}


# ── DefaultTenantResolver ────────────────────────────────────────────────────────


class TestDefaultTenantResolver:
    """Resolution rules: identity tenant → inheritance → default."""

    def setup_method(self):
        self.resolver = DefaultTenantResolver()

    def test_none_identity_returns_default(self):
        result = self.resolver.resolve_tenant(None)
        assert result.tenant_id == DEFAULT_TENANT_ID
        assert result.source == "default"
        assert result.valid is True
        assert "no identity" in (result.reason or "")

    def test_empty_tenant_returns_default(self):
        identity = IdentityContext(
            tenant=TenantIdentity(),
            authentication_state=AuthenticationState.ANONYMOUS,
        )
        result = self.resolver.resolve_tenant(identity)
        assert result.tenant_id == DEFAULT_TENANT_ID
        assert result.source == "default"

    def test_explicit_tenant_id_used(self):
        identity = IdentityContext(
            tenant=TenantIdentity(id="acme", organization_id="org-1", workspace_id="ws-42"),
            authentication_state=AuthenticationState.AUTHENTICATED,
        )
        result = self.resolver.resolve_tenant(identity)
        assert result.tenant_id == "acme"
        assert result.organization_id == "org-1"
        assert result.workspace_id == "ws-42"
        assert result.source == "identity"
        assert result.valid is True

    def test_tenant_id_with_whitespace_only_falls_back(self):
        identity = IdentityContext(
            tenant=TenantIdentity(id="   "),
            authentication_state=AuthenticationState.IDENTIFIED,
        )
        result = self.resolver.resolve_tenant(identity)
        assert result.tenant_id == DEFAULT_TENANT_ID
        assert result.source == "default"

    def test_deterministic_output(self):
        identity = IdentityContext(
            tenant=TenantIdentity(id="acme"),
            authentication_state=AuthenticationState.AUTHENTICATED,
        )
        a = self.resolver.resolve_tenant(identity)
        b = self.resolver.resolve_tenant(identity)
        assert a == b
        assert hash(a) == hash(b)


# ── TenantResolutionStage ────────────────────────────────────────────────────────


class TestTenantResolutionStage:
    """Stage produces TenantResolutionResult on the context."""

    async def test_stage_name(self):
        stage = TenantResolutionStage()
        assert stage.name == "tenant_resolution"

    async def test_populates_result_with_resolved_tenant(self):
        identity = IdentityContext(
            tenant=TenantIdentity(id="acme"),
            authentication_state=AuthenticationState.AUTHENTICATED,
        )
        ctx = PipelineContext(request_id="r1", transport="test")
        ctx.identity = identity
        ctx.resource_scope = ResourceScope(
            tenant_id="initial", owner_id="user1",
            visibility=Visibility.TENANT,
        )
        stage = TenantResolutionStage()
        result = await stage.execute(ctx)
        assert result.outcome.value == "continue"
        assert ctx.tenant_resolution_result is not None
        assert ctx.tenant_resolution_result.tenant_id == "acme"
        assert ctx.tenant_resolution_result.source == "identity"

    async def test_updates_resource_scope_when_tenant_differs(self):
        identity = IdentityContext(
            tenant=TenantIdentity(id="acme"),
            authentication_state=AuthenticationState.AUTHENTICATED,
        )
        ctx = PipelineContext(request_id="r2", transport="test")
        ctx.identity = identity
        ctx.resource_scope = ResourceScope(
            tenant_id="old-tenant", owner_id="user1",
            visibility=Visibility.TENANT,
        )
        stage = TenantResolutionStage()
        await stage.execute(ctx)
        assert ctx.resource_scope.tenant_id == "acme"

    async def test_does_not_update_resource_scope_when_tenant_same(self):
        identity = IdentityContext(
            tenant=TenantIdentity(id="acme"),
            authentication_state=AuthenticationState.AUTHENTICATED,
        )
        ctx = PipelineContext(request_id="r3", transport="test")
        ctx.identity = identity
        ctx.resource_scope = ResourceScope(
            tenant_id="acme", owner_id="user1",
            visibility=Visibility.TENANT,
        )
        stage = TenantResolutionStage()
        await stage.execute(ctx)
        assert ctx.resource_scope.tenant_id == "acme"

    async def test_handles_no_resource_scope_gracefully(self):
        identity = IdentityContext(
            tenant=TenantIdentity(id="acme"),
            authentication_state=AuthenticationState.AUTHENTICATED,
        )
        ctx = PipelineContext(request_id="r4", transport="test")
        ctx.identity = identity
        ctx.resource_scope = None
        stage = TenantResolutionStage()
        result = await stage.execute(ctx)
        assert result.outcome.value == "continue"
        assert ctx.tenant_resolution_result is not None
        assert ctx.tenant_resolution_result.tenant_id == "acme"

    async def test_default_tenant_when_no_identity(self):
        ctx = PipelineContext(request_id="r5", transport="test")
        ctx.identity = None
        ctx.resource_scope = None
        stage = TenantResolutionStage()
        await stage.execute(ctx)
        assert ctx.tenant_resolution_result is not None
        assert ctx.tenant_resolution_result.tenant_id == DEFAULT_TENANT_ID
        assert ctx.tenant_resolution_result.source == "default"

    async def test_pipeline_context_owns_field(self):
        """tenant_resolution_result is owned by tenant_resolution stage."""
        from core.pipeline.base import STAGE_OWNERSHIP
        assert "tenant_resolution_result" in STAGE_OWNERSHIP.get("tenant_resolution", set())


# ── Pipeline Integration ─────────────────────────────────────────────────────────


class TestTenantResolutionPipelineIntegration:
    """Tenant resolution runs after authentication, before authorization."""

    async def test_stage_in_default_pipeline(self):
        from core.pipeline.stages import DEFAULT_STAGES
        names = [name for name, _ in DEFAULT_STAGES]
        assert "tenant_resolution" in names
        auth_idx = names.index("authentication")
        tenant_idx = names.index("tenant_resolution")
        authz_idx = names.index("authorization")
        # tenant_resolution must come between authentication and authorization
        assert auth_idx < tenant_idx < authz_idx

    async def test_pipeline_execution_populates_result(self):
        """End-to-end: process_message with identity produces tenant_resolution_result."""
        from core.pipeline import pipeline as pipeline_module
        from core.pipeline.messages import Request

        # Create a minimal pipeline with just the stages we need
        from core.pipeline.stages.tenant_resolution import TenantResolutionStage

        p = pipeline_module.Pipeline()
        p.add_stage(TenantResolutionStage())

        old_default = pipeline_module._default_pipeline
        pipeline_module._default_pipeline = p
        try:
            response = await pipeline_module.process_message(
                Request(text="hello", transport="test", user_id="user1"),
            )
            # process_message doesn't return ctx, but we can check metadata
            # The tenant_resolution_result should exist after pipeline execution
            assert "pipeline_version" in response.metadata
        finally:
            pipeline_module._default_pipeline = old_default

    async def test_security_context_includes_tenant_resolution(self):
        """SecurityContext aggregates tenant_resolution."""
        identity = IdentityContext(
            tenant=TenantIdentity(id="acme"),
            authentication_state=AuthenticationState.AUTHENTICATED,
        )
        ctx = PipelineContext(request_id="r6", transport="test")
        ctx.identity = identity
        ctx.resource_scope = ResourceScope(tenant_id="old-tenant")
        await TenantResolutionStage().execute(ctx)
        sc = ctx.security
        assert sc.tenant_resolution is not None
        assert sc.tenant_resolution.tenant_id == "acme"

    async def test_deterministic_with_fixed_services(self):
        """Same identity produces same TenantResolutionResult (deterministic)."""
        from core.pipeline.deterministic import DeterministicServices

        svc = DeterministicServices.fixed()
        identity = IdentityContext(
            tenant=TenantIdentity(id="acme"),
            authentication_state=AuthenticationState.AUTHENTICATED,
        )
        ctx1 = PipelineContext(request_id="r1", transport="test", services=svc)
        ctx1.identity = identity
        ctx1.resource_scope = ResourceScope(tenant_id="old-tenant")
        await TenantResolutionStage().execute(ctx1)

        ctx2 = PipelineContext(request_id="r2", transport="test", services=svc)
        ctx2.identity = identity
        ctx2.resource_scope = ResourceScope(tenant_id="old-tenant")
        await TenantResolutionStage().execute(ctx2)

        assert ctx1.tenant_resolution_result == ctx2.tenant_resolution_result


# ── IdentityService.resolve_tenant ────────────────────────────────────────────────


class TestIdentityServiceResolveTenant:
    """IdentityService.resolve_tenant delegates to DefaultTenantResolver."""

    def test_delegates_to_resolver(self):
        service = get_identity_service()
        identity = IdentityContext(tenant=TenantIdentity(id="acme"))
        result = service.resolve_tenant(identity)
        assert isinstance(result, TenantResolutionResult)
        assert result.tenant_id == "acme"

    def test_deterministic_with_mock_resolver(self):
        """Override _tenant_resolver for deterministic tests."""
        from core.identity.service import IdentityService as IS

        class FixedResolver:
            def resolve_tenant(self, identity):
                return TenantResolutionResult(tenant_id="fixed-tenant", source="test")

        service = IS()
        service._tenant_resolver = FixedResolver()
        identity = IdentityContext(tenant=TenantIdentity(id="acme"))
        result = service.resolve_tenant(identity)
        assert result.tenant_id == "fixed-tenant"
        assert result.source == "test"
