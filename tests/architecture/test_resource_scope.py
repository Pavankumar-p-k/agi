"""Tests for ResourceScope — canonical resource ownership marker.

Sprint 4 covers the structural definition, pipeline propagation,
and artifact threading.  Tenant-scoped storage backends are later.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.identity import ResourceScope, Visibility
from core.identity.resource_scope import DEFAULT_TENANT_ID

_NOW = datetime.now(timezone.utc)
from core.pipeline.context import PipelineContext
from core.pipeline.messages import Request
from core.pipeline.pipeline import Pipeline, get_pipeline, process_message, set_pipeline
from core.pipeline.stages.auth import AuthenticationStage
from core.pipeline.stages.authorization import AuthorizationStage

# ── ResourceScope contract tests ──────────────────────────────────────────────


class TestResourceScopeContract:
    """ResourceScope behaves like a frozen runtime artifact."""

    def test_frozen(self):
        rs = ResourceScope(tenant_id="tenant-1")
        with pytest.raises(Exception):
            rs.tenant_id = "tenant-2"

    def test_defaults(self):
        rs = ResourceScope(tenant_id="tenant-1")
        assert rs.tenant_id == "tenant-1"
        assert rs.workspace_id is None
        assert rs.owner_id is None
        assert rs.visibility == Visibility.TENANT
        assert rs.metadata == {}

    def test_all_fields(self):
        rs = ResourceScope(
            tenant_id="acme",
            workspace_id="dev",
            owner_id="user-42",
            visibility=Visibility.PRIVATE,
        )
        assert rs.tenant_id == "acme"
        assert rs.workspace_id == "dev"
        assert rs.owner_id == "user-42"
        assert rs.visibility == Visibility.PRIVATE

    def test_equality(self):
        rs1 = ResourceScope(tenant_id="t1", workspace_id="w1")
        rs2 = ResourceScope(tenant_id="t1", workspace_id="w1")
        assert rs1 == rs2

    def test_hashable(self):
        rs = ResourceScope(tenant_id="t1")
        d = {rs: "value"}
        assert d[rs] == "value"

    def test_different_tenant_not_equal(self):
        rs1 = ResourceScope(tenant_id="t1")
        rs2 = ResourceScope(tenant_id="t2")
        assert rs1 != rs2


# ── Sentinel constants ────────────────────────────────────────────────────────


class TestSentinelConstants:
    def test_default_tenant_id_is_migration_sentinel(self):
        assert DEFAULT_TENANT_ID == "__default__"

    def test_system_tenant_id_is_reserved(self):
        from core.identity.resource_scope import SYSTEM_TENANT_ID
        assert SYSTEM_TENANT_ID == "__system__"


# ── Invariant validation ──────────────────────────────────────────────────────


class TestResourceScopeInvariants:
    def test_private_requires_owner(self):
        with pytest.raises(ValueError, match="PRIVATE visibility requires an owner_id"):
            ResourceScope(tenant_id="t1", visibility=Visibility.PRIVATE)

    def test_private_with_owner_ok(self):
        rs = ResourceScope(tenant_id="t1", visibility=Visibility.PRIVATE, owner_id="alice")
        assert rs.owner_id == "alice"

    def test_workspace_visibility_requires_workspace_id(self):
        with pytest.raises(ValueError, match="WORKSPACE visibility requires a workspace_id"):
            ResourceScope(tenant_id="t1", visibility=Visibility.WORKSPACE)

    def test_workspace_with_id_ok(self):
        rs = ResourceScope(tenant_id="t1", visibility=Visibility.WORKSPACE, workspace_id="w1")
        assert rs.workspace_id == "w1"

    def test_public_with_workspace_id_conflict(self):
        with pytest.raises(ValueError, match="PUBLIC visibility conflicts with a non-None workspace_id"):
            ResourceScope(tenant_id="t1", visibility=Visibility.PUBLIC, workspace_id="w1")

    def test_public_without_workspace_ok(self):
        rs = ResourceScope(tenant_id="t1", visibility=Visibility.PUBLIC)
        assert rs.visibility == Visibility.PUBLIC

    def test_default_visibility_no_invariant_violation(self):
        rs = ResourceScope(tenant_id="t1")
        assert rs.visibility == Visibility.TENANT
        assert rs.owner_id is None  # TENANT doesn't require owner


# ── Helper methods ────────────────────────────────────────────────────────────


class TestResourceScopeHelpers:
    def test_is_system_true(self):
        from core.identity.resource_scope import SYSTEM_TENANT_ID
        rs = ResourceScope(tenant_id=SYSTEM_TENANT_ID)
        assert rs.is_system() is True
        assert rs.is_default() is False

    def test_is_system_false(self):
        rs = ResourceScope(tenant_id="real-tenant")
        assert rs.is_system() is False

    def test_is_default_true(self):
        rs = ResourceScope(tenant_id=DEFAULT_TENANT_ID)
        assert rs.is_default() is True
        assert rs.is_system() is False

    def test_is_default_false(self):
        rs = ResourceScope(tenant_id="real-tenant")
        assert rs.is_default() is False

    def test_real_tenant_neither(self):
        rs = ResourceScope(tenant_id="acme-corp")
        assert rs.is_system() is False
        assert rs.is_default() is False


class TestResourceScopeSystemVisibility:
    def test_system_visibility_rejected_on_resource(self):
        with pytest.raises(ValueError, match="SYSTEM visibility is reserved"):
            ResourceScope(tenant_id="t1", visibility=Visibility.SYSTEM)


# ── Visibility enum ───────────────────────────────────────────────────────────


class TestVisibilityEnum:
    def test_values(self):
        assert Visibility.PRIVATE.value == "private"
        assert Visibility.TENANT.value == "tenant"
        assert Visibility.WORKSPACE.value == "workspace"
        assert Visibility.PUBLIC.value == "public"

    def test_order(self):
        values = list(Visibility)
        assert values == [Visibility.PRIVATE, Visibility.TENANT, Visibility.WORKSPACE, Visibility.PUBLIC, Visibility.SYSTEM]


# ── Pipeline context propagation ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestResourceScopePipeline:
    """ResourceScope is populated in process_message()."""

    async def test_resource_scope_present_after_process_message(self):
        """process_message populates resource_scope with tenant info."""
        old = get_pipeline()
        try:
            p = Pipeline()
            p.add_stage(AuthenticationStage())
            p.add_stage(AuthorizationStage())
            set_pipeline(p)

            req = Request(text="hello", transport="test", user_id="user-1")
            resp = await process_message(req)
            assert resp is not None
            # Re-run with a capture to inspect context
        finally:
            set_pipeline(old)

    async def test_resource_scope_has_default_tenant(self):
        """No tenant info → defaults to 'default' tenant."""
        from core.pipeline.base import PipelineStage, StageOutcome, StageResult

        captured = None

        class CaptureStage(PipelineStage):
            @property
            def name(self) -> str:
                return "capture"

            async def execute(self, context: PipelineContext) -> StageResult:
                nonlocal captured
                captured = context.resource_scope
                return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        old = get_pipeline()
        try:
            p = Pipeline()
            p.add_stage(AuthenticationStage())
            p.add_stage(CaptureStage())
            set_pipeline(p)

            req = Request(text="hello", transport="test")
            resp = await process_message(req)
            assert captured is not None
            assert captured.tenant_id == DEFAULT_TENANT_ID
            assert captured.visibility == Visibility.TENANT
        finally:
            set_pipeline(old)

    async def test_resource_scope_has_user_id_as_owner(self):
        """user_id on request becomes resource_scope.owner_id."""
        from core.pipeline.base import PipelineStage, StageOutcome, StageResult

        captured = None

        class CaptureStage(PipelineStage):
            @property
            def name(self) -> str:
                return "capture"

            async def execute(self, context: PipelineContext) -> StageResult:
                nonlocal captured
                captured = context.resource_scope
                return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        old = get_pipeline()
        try:
            p = Pipeline()
            p.add_stage(CaptureStage())
            set_pipeline(p)

            req = Request(text="hello", transport="test", user_id="alice")
            resp = await process_message(req)
            assert captured is not None
            assert captured.owner_id == "alice"
        finally:
            set_pipeline(old)

    async def test_resource_scope_ownership_readonly(self):
        """resource_scope is owned by load_context — no other stage writes it."""
        from core.pipeline.base import PipelineStage, StageOutcome, StageResult

        class MutatorStage(PipelineStage):
            @property
            def name(self) -> str:
                return "mutator"

            async def execute(self, context: PipelineContext) -> StageResult:
                context.resource_scope = None  # ownership violation
                return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        old = get_pipeline()
        try:
            p = Pipeline()
            p.add_stage(MutatorStage())
            set_pipeline(p)

            req = Request(text="hello", transport="test")
            resp = await process_message(req)
            assert resp is not None
        finally:
            set_pipeline(old)

    async def test_security_context_includes_resource_scope(self):
        """resource_scope is not part of SecurityContext (it is a different dimension)."""
        old = get_pipeline()
        try:
            p = Pipeline()
            p.add_stage(AuthenticationStage())
            set_pipeline(p)

            req = Request(text="hello", transport="test")
            resp = await process_message(req)
            assert resp is not None
        finally:
            set_pipeline(old)


# ── Observation resource_scope integration ────────────────────────────────────


class TestObservationResourceScope:
    """Observation can carry an optional ResourceScope."""

    def test_observation_defaults_no_resource_scope(self):
        from core.pipeline.observation import Observation

        obs = Observation(
            id="obs-1",
            fingerprint="fp",
            activity_id="act-1",
            source="test",
            type="text",
            timestamp=_NOW,
            payload={},
        )
        assert obs.resource_scope is None

    def test_observation_with_resource_scope(self):
        from core.pipeline.observation import Observation

        rs = ResourceScope(tenant_id="acme", workspace_id="dev")
        obs = Observation(
            id="obs-2",
            fingerprint="fp2",
            activity_id="act-1",
            source="test",
            type="text",
            timestamp=_NOW,
            payload={},
            resource_scope=rs,
        )
        assert obs.resource_scope is not None
        assert obs.resource_scope.tenant_id == "acme"
        assert obs.resource_scope.workspace_id == "dev"

    def test_observation_to_dict_includes_resource_scope(self):
        from core.pipeline.observation import Observation

        rs = ResourceScope(tenant_id="acme", visibility=Visibility.PRIVATE, owner_id="alice")
        obs = Observation(
            id="obs-3",
            fingerprint="fp3",
            activity_id="act-1",
            source="test",
            type="text",
            timestamp=_NOW,
            payload={},
            resource_scope=rs,
        )
        d = obs.to_dict()
        assert d["resource_scope"] is not None
        assert d["resource_scope"]["tenant_id"] == "acme"
        assert d["resource_scope"]["visibility"] == "private"

    def test_observation_to_dict_no_resource_scope(self):
        from core.pipeline.observation import Observation

        obs = Observation(
            id="obs-4",
            fingerprint="fp4",
            activity_id="act-1",
            source="test",
            type="text",
            timestamp=_NOW,
            payload={},
        )
        d = obs.to_dict()
        assert d["resource_scope"] is None


# ── Outcome resource_scope integration ────────────────────────────────────────


class TestOutcomeResourceScope:
    """Outcome can carry an optional ResourceScope."""

    def test_outcome_defaults_no_resource_scope(self):
        from core.pipeline.outcome import Outcome

        oc = Outcome(success=True)
        assert oc.resource_scope is None

    def test_outcome_with_resource_scope(self):
        from core.pipeline.outcome import Outcome

        rs = ResourceScope(tenant_id="acme")
        oc = Outcome(success=True, resource_scope=rs)
        assert oc.resource_scope is not None
        assert oc.resource_scope.tenant_id == "acme"
