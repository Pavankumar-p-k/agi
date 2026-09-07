"""Tests for ResourceAccessStage and resource access enforcement.

Sprint 5: covers ResourceAccessResult, the visibility matrix,
replay determinism, and pipeline integration.

Visibility matrix:
  PRIVATE:   owner ✓,  non-owner ✗
  WORKSPACE: same ws ✓, other ws ✗
  TENANT:    same tnt ✓, other tnt ✗
  PUBLIC:    everyone ✓
  SYSTEM:    system ✓, others ✗
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.identity.models import (
    AgentIdentity,
    AuthenticationState,
    IdentityContext,
    TenantIdentity,
    UserIdentity,
)
from core.identity.resource_scope import ResourceScope, Visibility
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.messages import Request
from core.pipeline.pipeline import Pipeline, get_pipeline, process_message, set_pipeline
from core.pipeline.resource_access_result import ResourceAccessResult
from core.pipeline.stages.auth import AuthenticationStage
from core.pipeline.stages.authorization import AuthorizationStage
from core.pipeline.stages.resource_access import ResourceAccessStage

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_identity(
    user_id: str | None = None,
    state: AuthenticationState = AuthenticationState.ANONYMOUS,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> IdentityContext:
    user = UserIdentity(id=user_id) if user_id else None
    agent = AgentIdentity(id="test", type="test")
    tenant = TenantIdentity(id=tenant_id, workspace_id=workspace_id) if tenant_id else TenantIdentity()
    return IdentityContext(
        user=user,
        agent=agent,
        tenant=tenant,
        authentication_state=state,
    )


class _CapturingStage(PipelineStage):
    """Captures context fields after resource access."""

    @property
    def name(self) -> str:
        return "capture"

    async def execute(self, context: PipelineContext) -> StageResult:
        self.captured = context.resource_access_result
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


async def _run(
    identity: IdentityContext | None,
    scope: ResourceScope | None,
    action: str = "read",
) -> ResourceAccessResult | None:
    capture = _CapturingStage()
    p = Pipeline()
    p.add_stage(ResourceAccessStage())
    p.add_stage(capture)

    ctx = PipelineContext(request_id="test-ra", transport="test", raw_input="hello")
    ctx.identity = identity
    ctx.resource_scope = scope
    ctx.metadata["resource_action"] = action
    await p.execute(ctx)
    return capture.captured


# ═══════════════════════════════════════════════════════════════════════════════
# ResourceAccessResult contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestResourceAccessResultContract:
    def test_frozen(self):
        rs = ResourceScope(tenant_id="t1")
        r = ResourceAccessResult(
            allowed=True, reason="ok", resource_scope=rs,
            requested_action="read", effective_visibility=Visibility.PUBLIC,
        )
        with pytest.raises(Exception):
            r.allowed = False

    def test_equality(self):
        rs = ResourceScope(tenant_id="t1")
        r1 = ResourceAccessResult(allowed=True, reason="ok", resource_scope=rs, requested_action="read", effective_visibility=Visibility.PUBLIC)
        r2 = ResourceAccessResult(allowed=True, reason="ok", resource_scope=rs, requested_action="read", effective_visibility=Visibility.PUBLIC)
        assert r1 == r2

    def test_hashable(self):
        rs = ResourceScope(tenant_id="t1")
        r = ResourceAccessResult(allowed=True, reason="ok", resource_scope=rs, requested_action="read", effective_visibility=Visibility.PUBLIC)
        d = {r: "value"}
        assert d[r] == "value"


# ═══════════════════════════════════════════════════════════════════════════════
# Visibility matrix
# ═══════════════════════════════════════════════════════════════════════════════


class TestVisibilityPublic:
    """PUBLIC: everyone allowed."""

    @pytest.mark.asyncio
    async def test_anonymous_allowed(self):
        identity = _make_identity()
        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PUBLIC)
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is True
        assert result.reason == "public resource"
        assert result.effective_visibility == Visibility.PUBLIC

    @pytest.mark.asyncio
    async def test_authenticated_allowed(self):
        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED)
        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PUBLIC)
        result = await _run(identity, scope)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_no_identity_allowed(self):
        """PUBLIC allows access even without identity context."""
        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PUBLIC)
        result = await _run(identity=None, scope=scope)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_default_action(self):
        identity = _make_identity()
        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PUBLIC)
        ctx = PipelineContext(request_id="r", transport="test", raw_input="h")
        ctx.identity = identity
        ctx.resource_scope = scope
        capture = _CapturingStage()
        p = Pipeline()
        p.add_stage(ResourceAccessStage())
        p.add_stage(capture)
        await p.execute(ctx)
        assert capture.captured is not None
        assert capture.captured.requested_action == "read"


class TestVisibilityPrivate:
    """PRIVATE: owner only."""

    @pytest.mark.asyncio
    async def test_owner_allowed(self):
        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED)
        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PRIVATE, owner_id="alice")
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is True
        assert result.reason == "owner access granted"
        assert result.effective_visibility == Visibility.PRIVATE

    @pytest.mark.asyncio
    async def test_non_owner_denied(self):
        identity = _make_identity(user_id="bob", state=AuthenticationState.AUTHENTICATED)
        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PRIVATE, owner_id="alice")
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is False
        assert result.reason == "non-owner access denied"

    @pytest.mark.asyncio
    async def test_no_user_identity_denied(self):
        identity = _make_identity(state=AuthenticationState.AUTHENTICATED)
        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PRIVATE, owner_id="alice")
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_anonymous_denied(self):
        identity = _make_identity()
        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PRIVATE, owner_id="alice")
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is False


class TestVisibilityTenant:
    """TENANT: same tenant allowed, cross-tenant denied."""

    @pytest.mark.asyncio
    async def test_same_tenant_allowed(self):
        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED, tenant_id="acme")
        scope = ResourceScope(tenant_id="acme", visibility=Visibility.TENANT)
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is True
        assert result.reason == "same tenant"
        assert result.effective_visibility == Visibility.TENANT

    @pytest.mark.asyncio
    async def test_cross_tenant_denied(self):
        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED, tenant_id="acme")
        scope = ResourceScope(tenant_id="other-corp", visibility=Visibility.TENANT)
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is False
        assert result.reason == "cross-tenant access denied"

    @pytest.mark.asyncio
    async def test_no_tenant_denied(self):
        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED)
        scope = ResourceScope(tenant_id="acme", visibility=Visibility.TENANT)
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_anonymous_denied(self):
        identity = _make_identity()
        scope = ResourceScope(tenant_id="acme", visibility=Visibility.TENANT)
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is False


class TestVisibilityWorkspace:
    """WORKSPACE: same workspace allowed, cross-workspace denied."""

    @pytest.mark.asyncio
    async def test_same_workspace_allowed(self):
        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED, tenant_id="acme", workspace_id="dev")
        scope = ResourceScope(tenant_id="acme", workspace_id="dev", visibility=Visibility.WORKSPACE)
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is True
        assert result.reason == "same workspace"
        assert result.effective_visibility == Visibility.WORKSPACE

    @pytest.mark.asyncio
    async def test_cross_workspace_denied(self):
        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED, tenant_id="acme", workspace_id="dev")
        scope = ResourceScope(tenant_id="acme", workspace_id="prod", visibility=Visibility.WORKSPACE)
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is False
        assert result.reason == "cross-workspace access denied"

    @pytest.mark.asyncio
    async def test_cross_tenant_workspace_denied(self):
        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED, tenant_id="acme", workspace_id="dev")
        scope = ResourceScope(tenant_id="other", workspace_id="dev", visibility=Visibility.WORKSPACE)
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_no_workspace_in_identity_denied(self):
        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED, tenant_id="acme")
        scope = ResourceScope(tenant_id="acme", workspace_id="dev", visibility=Visibility.WORKSPACE)
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is False


class TestVisibilitySystem:
    """SYSTEM: system identity only."""

    @pytest.mark.asyncio
    async def test_system_allowed(self):
        identity = _make_identity(user_id="scheduler", state=AuthenticationState.SYSTEM)
        scope = ResourceScope(tenant_id="acme", visibility=Visibility.PRIVATE, owner_id="other")
        result = await _run(identity, scope)
        assert result is not None
        assert result.allowed is True
        assert result.reason == "system identity"
        assert result.effective_visibility == Visibility.SYSTEM

    @pytest.mark.asyncio
    async def test_system_allows_any_scope(self):
        identity = _make_identity(user_id="scheduler", state=AuthenticationState.SYSTEM)
        scope = ResourceScope(tenant_id="other-corp", visibility=Visibility.PRIVATE, owner_id="stranger")
        result = await _run(identity, scope)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_non_system_denied(self):
        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED)
        scope = ResourceScope(tenant_id="acme", visibility=Visibility.PRIVATE, owner_id="alice")
        result = await _run(identity, scope)
        assert result is not None


class TestNoScope:
    """No resource scope on context."""

    @pytest.mark.asyncio
    async def test_no_scope_denied(self):
        identity = _make_identity()
        result = await _run(identity, scope=None)
        assert result is not None
        assert result.allowed is False
        assert result.reason == "no resource scope"


# ═══════════════════════════════════════════════════════════════════════════════
# ResourceGrant integration
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestGrantExpiry:
    """ResourceAccessStage respects expired ResourceGrant."""

    async def test_expired_grant_denies(self):
        from datetime import datetime, timedelta, timezone
        from core.pipeline.resource_grant import ResourceGrant

        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PUBLIC)
        identity = _make_identity(user_id="alice")
        grant = ResourceGrant(
            subject_id="alice",
            scope=scope,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        capture = _CapturingStage()
        p = Pipeline()
        p.add_stage(ResourceAccessStage())
        p.add_stage(capture)

        ctx = PipelineContext(request_id="r", transport="test", raw_input="h")
        ctx.identity = identity
        ctx.resource_scope = scope
        ctx.resource_grant = grant
        await p.execute(ctx)
        assert capture.captured is not None
        assert capture.captured.allowed is False
        assert "expired" in capture.captured.reason

    async def test_valid_grant_allows_visibility_check(self):
        from datetime import datetime, timedelta, timezone
        from core.pipeline.resource_grant import ResourceGrant

        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PUBLIC)
        identity = _make_identity(user_id="alice")
        grant = ResourceGrant(
            subject_id="alice",
            scope=scope,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        capture = _CapturingStage()
        p = Pipeline()
        p.add_stage(ResourceAccessStage())
        p.add_stage(capture)

        ctx = PipelineContext(request_id="r", transport="test", raw_input="h")
        ctx.identity = identity
        ctx.resource_scope = scope
        ctx.resource_grant = grant
        await p.execute(ctx)
        assert capture.captured is not None
        assert capture.captured.allowed is True  # PUBLIC + valid grant

    async def test_expired_grant_overrides_public(self):
        from datetime import datetime, timedelta, timezone
        from core.pipeline.resource_grant import ResourceGrant

        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PUBLIC)
        identity = _make_identity(user_id="alice")
        grant = ResourceGrant(
            subject_id="alice",
            scope=scope,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        capture = _CapturingStage()
        p = Pipeline()
        p.add_stage(ResourceAccessStage())
        p.add_stage(capture)

        ctx = PipelineContext(request_id="r", transport="test", raw_input="h")
        ctx.identity = identity
        ctx.resource_scope = scope
        ctx.resource_grant = grant
        await p.execute(ctx)
        assert capture.captured is not None
        assert capture.captured.allowed is False  # expired overrides PUBLIC


# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline integration
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestPipelineWithResourceAccess:
    """Full pipeline execution with ResourceAccessStage."""

    async def test_presents_result_after_execution(self):
        old = get_pipeline()
        try:
            capture = _CapturingStage()
            p = Pipeline()
            p.add_stage(ResourceAccessStage())
            p.add_stage(capture)
            set_pipeline(p)

            req = Request(text="hello", transport="test")
            resp = await process_message(req)
            assert resp is not None
            assert capture.captured is not None
        finally:
            set_pipeline(old)

    async def test_no_scope_no_crash(self):
        capture = _CapturingStage()
        p = Pipeline()
        p.add_stage(ResourceAccessStage())
        p.add_stage(capture)

        ctx = PipelineContext(request_id="r", transport="test", raw_input="h")
        ctx.identity = _make_identity()
        ctx.resource_scope = None
        await p.execute(ctx)
        assert capture.captured is not None
        assert capture.captured.allowed is False

    async def test_does_not_mutate_identity_or_scope(self):
        capture = _CapturingStage()
        p = Pipeline()
        p.add_stage(ResourceAccessStage())
        p.add_stage(capture)

        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED)
        scope = ResourceScope(tenant_id="t1", visibility=Visibility.PUBLIC)
        ctx = PipelineContext(request_id="r", transport="test", raw_input="h")
        ctx.identity = identity
        ctx.resource_scope = scope
        await p.execute(ctx)
        assert ctx.identity is identity
        assert ctx.resource_scope is scope


# ═══════════════════════════════════════════════════════════════════════════════
# Replay determinism
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestResourceAccessReplay:
    """Same identity + same scope → identical ResourceAccessResult."""

    async def test_replay_deterministic(self):
        identity = _make_identity(user_id="alice", state=AuthenticationState.AUTHENTICATED, tenant_id="acme")
        scope = ResourceScope(tenant_id="acme", visibility=Visibility.TENANT)

        async def _run_once() -> ResourceAccessResult:
            capture = _CapturingStage()
            p = Pipeline()
            p.add_stage(ResourceAccessStage())
            p.add_stage(capture)
            ctx = PipelineContext(request_id=id, transport="test", raw_input="h")
            ctx.identity = identity
            ctx.resource_scope = scope
            ctx.metadata["resource_action"] = "write"
            await p.execute(ctx)
            return capture.captured

        r1 = await _run_once()
        r2 = await _run_once()
        assert r1 is not None and r2 is not None
        assert r1.allowed == r2.allowed
        assert r1.reason == r2.reason
        assert r1.requested_action == r2.requested_action
        assert r1.effective_visibility == r2.effective_visibility
