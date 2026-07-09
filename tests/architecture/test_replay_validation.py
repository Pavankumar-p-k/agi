"""Sprint 5.5B — Replay Validation + Rule 30 (ResourceScope propagation).

Records a Request → Pipeline → Outcome execution, then replays with the
same deterministic services and mocked provider.  Asserts structural
identity of all architecture artifacts.
"""
from __future__ import annotations

from typing import Any

import pytest

from core.identity import ResourceScope, Visibility
from core.pipeline.context import PipelineContext
from core.pipeline.deterministic import DeterministicServices
from core.pipeline.observation import Observation
from core.pipeline.outcome import Outcome
from core.pipeline.pipeline import Pipeline
from core.pipeline.stages.execution import (
    ExecutionStage,
    Provider,
    ProviderResult,
    Runtime,
)
from core.pipeline.store_decision import StoreDecision
from core.pipeline.stages.verification import Verdict


# ── Fake provider that returns canned responses ─────────────────────────────


class FakeProvider(Provider):
    """Mock LLM provider that returns the same text every call."""

    def __init__(self, text: str = "fake response"):
        self._text = text

    @property
    def name(self) -> str:
        return "fake"

    async def complete(self, prompt: str, **kwargs) -> ProviderResult:
        return ProviderResult(text=self._text, provider="fake", tokens=0)


# ── Helper ──────────────────────────────────────────────────────────────────


def _make_pipeline(text: str = "fake") -> Pipeline:
    """A single-stage pipeline with a fake provider."""
    stage = ExecutionStage()
    stage.provider_manager.add_provider(FakeProvider(text), position=0)
    p = Pipeline()
    p.add_stage(stage)
    return p


async def _run(pipeline: Pipeline, svc: DeterministicServices, **overrides: object) -> PipelineContext:
    ctx = PipelineContext(
        request_id=svc.uuid4(),
        transport="test",
        services=svc,
        **overrides,
    )
    ctx.activity_id = ctx.request_id
    return await pipeline.execute(ctx)


# ── Replay tests ────────────────────────────────────────────────────────────


class TestReplayValidation:
    """Run the same request twice and verify structural identity."""

    @pytest.mark.asyncio
    async def test_replay_structural_snapshot(self):
        svc = DeterministicServices.fixed()

        async def run() -> dict:
            p = _make_pipeline("cloudy")
            ctx = await _run(p, svc)
            return {
                "execution_state": ctx.execution_state,
                "error": ctx.error,
                "outcome_success": ctx.outcome.success if ctx.outcome else None,
                "observation_count": len(ctx.outcome.observations) if ctx.outcome else 0,
            }

        assert await run() == await run()

    @pytest.mark.asyncio
    async def test_replay_observation_fingerprints_match(self):
        svc = DeterministicServices.fixed()

        async def exec_once() -> list[Observation]:
            p = _make_pipeline("sunny")
            ctx = await _run(p, svc, raw_input="How are you?")
            return list(ctx.outcome.observations) if ctx.outcome else []

        obs1 = await exec_once()
        obs2 = await exec_once()

        assert len(obs1) == len(obs2)
        for o1, o2 in zip(obs1, obs2):
            assert o1.fingerprint == o2.fingerprint
            assert o1.source == o2.source
            assert o1.type == o2.type
            assert o1.payload == o2.payload

    @pytest.mark.asyncio
    async def test_replay_with_preloaded_plan(self):
        svc = DeterministicServices.fixed()
        plan = {
            "goal": "test",
            "steps": [{"intent": "respond", "objective": "say hello"}],
        }

        async def run() -> dict:
            p = _make_pipeline("executed step 0")
            ctx = await _run(p, svc, raw_input="hello", plan=dict(plan), selected_capabilities={0: []})
            return {
                "execution_state": ctx.execution_state,
                "outcome_success": ctx.outcome.success if ctx.outcome else None,
                "observation_count": len(ctx.outcome.observations) if ctx.outcome else 0,
                "fingerprints": [o.fingerprint for o in ctx.outcome.observations] if ctx.outcome else [],
            }

        assert await run() == await run()

    @pytest.mark.asyncio
    async def test_replay_produces_identical_observations(self):
        svc = DeterministicServices.fixed()

        async def exec_once() -> list[Observation]:
            p = _make_pipeline("hello world")
            ctx = await _run(p, svc, raw_input="say hi")
            return list(ctx.outcome.observations) if ctx.outcome else []

        r1 = await exec_once()
        r2 = await exec_once()

        for o1, o2 in zip(r1, r2):
            assert o1.fingerprint == o2.fingerprint
            assert o1.payload == o2.payload
            assert o1.source == o2.source
            assert o1.type == o2.type


class TestOutcomeStructure:
    """Outcome has all required fields after execution."""

    @pytest.mark.asyncio
    async def test_outcome_has_all_fields(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_pipeline("result"), svc, raw_input="test")

        outcome = ctx.outcome
        assert outcome is not None
        assert outcome.success is True
        assert isinstance(outcome.observations, list)
        assert len(outcome.observations) > 0
        assert outcome.activity_id is not None
        assert outcome.metrics is not None

    @pytest.mark.asyncio
    async def test_outcome_observation_has_activity_id(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_pipeline("hello"), svc, raw_input="test")
        outcome = ctx.outcome
        assert outcome is not None
        assert outcome.activity_id is not None
        for obs in outcome.observations:
            assert obs.activity_id == outcome.activity_id

    @pytest.mark.asyncio
    async def test_outcome_is_immutable(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_pipeline("immutable"), svc, raw_input="test")
        outcome = ctx.outcome
        assert outcome is not None
        with pytest.raises(AttributeError):
            outcome.success = False  # type: ignore[misc]


# ── Rule 30: ResourceScope propagation ──────────────────────────────────────
# Every runtime artifact produced after LoadContext must carry the same
# immutable ResourceScope as PipelineContext.resource_scope.
#
# Propagation chain (all must be equal after execution):
#   PipelineContext.resource_scope
#       == Outcome.resource_scope
#       == every Observation.resource_scope
#       == ArchitectureMetrics.(tenant_id, workspace_id)


class TestResourceScopePropagation:
    """Rule 30: ResourceScope propagation from PipelineContext to all
    runtime artifacts produced after LoadContext."""

    @pytest.mark.asyncio
    async def test_resource_scope_in_architecture_metrics(self):
        """ctx.resource_scope.tenant_id is reflected in
        architecture_metrics after execution."""
        scope = ResourceScope(tenant_id="acme", visibility=Visibility.TENANT)
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_pipeline("metrics test"), svc,
                         raw_input="test", resource_scope=scope)

        metrics = ctx.architecture_metrics
        assert metrics is not None
        assert metrics.tenant_id == "acme"
        assert not metrics.workspace_id  # empty string when not set

    @pytest.mark.asyncio
    async def test_resource_scope_in_security_context(self):
        """ctx.security.resource_scope references the same ResourceScope."""
        scope = ResourceScope(tenant_id="acme", visibility=Visibility.TENANT)
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_pipeline("security test"), svc,
                         raw_input="test", resource_scope=scope)

        assert ctx.security is not None
        assert ctx.security.resource_scope is not None
        assert ctx.security.resource_scope.tenant_id == "acme"

    @pytest.mark.asyncio
    async def test_resource_scope_propagates_to_outcome(self):
        """Outcome.resource_scope must match PipelineContext.resource_scope."""
        scope = ResourceScope(tenant_id="acme", owner_id="user-1")
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_pipeline("outcome test"), svc,
                         raw_input="test", resource_scope=scope)

        assert ctx.outcome is not None
        assert ctx.outcome.resource_scope is not None
        assert ctx.outcome.resource_scope == scope

    @pytest.mark.asyncio
    async def test_resource_scope_propagates_to_observations(self):
        """Every Observation.resource_scope must match the scope set on
        PipelineContext."""
        scope = ResourceScope(tenant_id="acme", visibility=Visibility.WORKSPACE,
                              workspace_id="ws-1")
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_pipeline("obs test"), svc,
                         raw_input="test", resource_scope=scope)

        assert ctx.outcome is not None
        for obs in ctx.outcome.observations:
            assert obs.resource_scope is not None
            assert obs.resource_scope == scope

    @pytest.mark.asyncio
    async def test_full_propagation_chain(self):
        """All artifacts share the same ResourceScope after execution.

        Chain: PipelineContext → Outcome → every Observation → metrics.
        """
        scope = ResourceScope(tenant_id="chain-co", workspace_id="ws-2",
                              owner_id="user-2", visibility=Visibility.WORKSPACE)
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_pipeline("chain test"), svc,
                         raw_input="test", resource_scope=scope)

        assert ctx.outcome is not None
        outcome = ctx.outcome
        assert outcome.resource_scope == scope

        for obs in outcome.observations:
            assert obs.resource_scope == scope

        metrics = ctx.architecture_metrics
        assert metrics is not None
        assert metrics.tenant_id == scope.tenant_id
        assert metrics.workspace_id == scope.workspace_id

    @pytest.mark.asyncio
    async def test_propagation_replay_determinism(self):
        """Same request + same scope produces identical scope chain on replay."""
        scope = ResourceScope(tenant_id="replay-co", workspace_id="ws-r1",
                              owner_id="user-r", visibility=Visibility.PRIVATE)

        async def run() -> dict:
            svc = DeterministicServices.fixed()
            ctx = await _run(_make_pipeline("replay chain"), svc,
                             raw_input="test", resource_scope=scope)
            obs_scopes = [o.resource_scope for o in ctx.outcome.observations] if ctx.outcome else []
            return {
                "outcome_scope": ctx.outcome.resource_scope if ctx.outcome else None,
                "obs_scopes": obs_scopes,
                "metrics_tenant": ctx.architecture_metrics.tenant_id if ctx.architecture_metrics else None,
            }

        r1 = await run()
        r2 = await run()
        assert r1 == r2


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 6 — RuntimeContext replay
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestRuntimeContextReplay:
    """RuntimeContext construction is deterministic replayable."""

    async def test_runtime_context_from_deterministic_services(self):
        from datetime import datetime, timezone

        from core.identity.models import IdentityContext, AuthenticationState
        from core.identity.resource_scope import ResourceScope
        from core.identity.tenant_resolver import TenantResolutionResult
        from core.pipeline.authentication_result import AuthenticationResult
        from core.pipeline.authorization_result import AuthorizationResult
        from core.pipeline.resource_grant import ResourceGrant
        from core.runtime import RuntimeContext

        svc = DeterministicServices.fixed()
        aid = svc.uuid4()
        rid = svc.uuid4()

        ctx = RuntimeContext(
            identity=IdentityContext(authentication_state=AuthenticationState.ANONYMOUS),
            authentication=AuthenticationResult(authenticated=False, state=AuthenticationState.ANONYMOUS),
            authorization=AuthorizationResult(allowed=True, scope="chat.execute"),
            tenant=TenantResolutionResult(tenant_id="acme"),
            resource_scope=ResourceScope(tenant_id="acme"),
            resource_grant=ResourceGrant(
                subject_id="u1", scope=ResourceScope(tenant_id="acme"),
                issued_at=datetime.now(timezone.utc),
            ),
            activity_id=aid,
            request_id=rid,
        )
        assert ctx.activity_id == aid
        assert ctx.request_id == rid
        assert ctx.tenant.tenant_id == "acme"
        assert ctx.authorization.allowed

    async def test_runtime_context_replay_identity(self):
        """Fresh deterministic services → identical RuntimeContext on replay."""
        from datetime import datetime, timezone

        from core.identity.models import IdentityContext, AuthenticationState
        from core.identity.resource_scope import ResourceScope
        from core.identity.tenant_resolver import TenantResolutionResult
        from core.pipeline.authentication_result import AuthenticationResult
        from core.pipeline.authorization_result import AuthorizationResult
        from core.pipeline.resource_grant import ResourceGrant
        from core.runtime import RuntimeContext

        def build() -> RuntimeContext:
            svc = DeterministicServices.fake()
            aid = svc.uuid4()
            rid = svc.uuid4()
            return RuntimeContext(
                identity=IdentityContext(authentication_state=AuthenticationState.ANONYMOUS),
                authentication=AuthenticationResult(authenticated=False, state=AuthenticationState.ANONYMOUS),
                authorization=AuthorizationResult(allowed=True, scope="chat.execute"),
                tenant=TenantResolutionResult(tenant_id="replay"),
                resource_scope=ResourceScope(tenant_id="replay"),
                resource_grant=ResourceGrant(
                    subject_id="u1", scope=ResourceScope(tenant_id="replay"),
                    issued_at=datetime.now(timezone.utc),
                ),
                activity_id=aid,
                request_id=rid,
            )

        r1 = build()
        r2 = build()
        assert r1 == r2
        assert r1.activity_id == r2.activity_id
        assert r1.request_id == r2.request_id

    async def test_execution_runtime_with_fake_services(self):
        """ExecutionRuntime produces deterministic output with fake services."""
        from core.runtime import RuntimeContext
        from core.runtime.providers import ExecutionRuntime, RuntimeServices
        from core.runtime.protocols import (
            ActivityService,
            EventBus,
            MemoryService,
            MetricsService,
            ObservationService,
            SchedulerService,
        )

        records: list[dict] = []

        class FakeMemory(MemoryService):
            async def store_facts(self, ctx: RuntimeContext, facts: list[dict]) -> int:
                return 0
            async def search_facts(self, ctx: RuntimeContext, query: str, **kwargs) -> list[dict]:
                return []
            async def get_user_facts(self, ctx: RuntimeContext, user_id: str) -> list[dict]:
                return []

        class FakeObservation(ObservationService):
            async def publish(self, ctx: RuntimeContext, observation: Any) -> None:
                records.append({"type": "observation", "ctx_id": ctx.request_id})

        class FakeScheduler(SchedulerService):
            async def create_activity(self, ctx: RuntimeContext, goal: str, **kwargs) -> str:
                return "sched-1"
            async def get_queue(self, ctx: RuntimeContext) -> list[Any]:
                return []

        class FakeMetrics(MetricsService):
            def record(self, ctx: RuntimeContext, metrics: dict[str, Any]) -> None:
                records.append({"type": "metrics", "metrics": metrics})

        class FakeBus(EventBus):
            async def publish(self, ctx: RuntimeContext, event: Any) -> None:
                records.append({"type": "event", "ctx_id": ctx.request_id})
            async def subscribe(self, ctx: RuntimeContext, handler: Any) -> None:
                pass

        class FakeActivity(ActivityService):
            async def create_activity(self, ctx: RuntimeContext, goal: str) -> Any:
                return {"id": "act-1"}
            async def create_node(self, ctx: RuntimeContext, activity_id: str, **kwargs) -> Any:
                return {"id": "node-1"}

        services = RuntimeServices(
            memory=FakeMemory(),
            observation=FakeObservation(),
            scheduler=FakeScheduler(),
            metrics=FakeMetrics(),
            event_bus=FakeBus(),
            activity=FakeActivity(),
        )
        rt = ExecutionRuntime(services)

        from core.identity.models import IdentityContext, AuthenticationState
        from core.identity.resource_scope import ResourceScope
        from core.identity.tenant_resolver import TenantResolutionResult
        from core.pipeline.authentication_result import AuthenticationResult
        from core.pipeline.authorization_result import AuthorizationResult
        from core.pipeline.resource_grant import ResourceGrant
        from datetime import datetime, timezone

        svc = DeterministicServices.fixed()
        ctx = RuntimeContext(
            identity=IdentityContext(authentication_state=AuthenticationState.ANONYMOUS),
            authentication=AuthenticationResult(authenticated=False, state=AuthenticationState.ANONYMOUS),
            authorization=AuthorizationResult(allowed=True, scope="chat.execute"),
            tenant=TenantResolutionResult(tenant_id="acme"),
            resource_scope=ResourceScope(tenant_id="acme"),
            resource_grant=ResourceGrant(subject_id="u1", scope=ResourceScope(tenant_id="acme")),
            activity_id=svc.uuid4(),
            request_id=svc.uuid4(),
        )

        result = await rt.execute(ctx, plan={"steps": [{"intent": "respond", "objective": "say hi"}]})

        assert "text" in result
        assert len(records) > 0  # observations + metrics published
        assert any(r["type"] == "observation" for r in records)
        assert any(r["type"] == "metrics" for r in records)
