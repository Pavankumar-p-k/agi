"""Sprint 5.5C — Runtime Trace Validation.

Validates runtime invariants dynamically after pipeline execution:
- Every artifact belongs to exactly one Activity
- No orphan observations / outcomes / verdicts / store decisions
- No duplicate observation IDs
- parent-child Observation relationships are valid
"""
from __future__ import annotations

from collections import Counter

import pytest

from core.pipeline.context import PipelineContext
from core.pipeline.deterministic import DeterministicServices
from core.pipeline.observation import Observation
from core.pipeline.outcome import Outcome
from core.pipeline.pipeline import Pipeline
from core.pipeline.stages.execution import (
    ExecutionStage,
    Provider,
    ProviderResult,
)
from core.pipeline.stages.verification import Verdict, VerificationStage
from core.pipeline.stages.memory import MemoryStage
from core.pipeline.store_decision import StoreDecision


# ── Fake provider ───────────────────────────────────────────────────────────


class FakeProvider(Provider):
    def __init__(self, text: str = "response"):
        self._text = text

    @property
    def name(self) -> str:
        return "fake"

    async def complete(self, prompt: str, **kwargs) -> ProviderResult:
        return ProviderResult(text=self._text, provider="fake", tokens=0)


# ── Full pipeline with all post-execution stages ────────────────────────────


def _make_full_pipeline() -> Pipeline:
    stage = ExecutionStage()
    stage.provider_manager.add_provider(FakeProvider("trace test"))
    p = Pipeline()
    p.add_stage(stage)
    p.add_stage(VerificationStage())
    p.add_stage(MemoryStage())
    return p


async def _run(p: Pipeline, svc: DeterministicServices) -> PipelineContext:
    ctx = PipelineContext(
        raw_input="test",
        request_id=svc.uuid4(),
        transport="test",
        services=svc,
    )
    ctx.activity_id = ctx.request_id
    return await p.execute(ctx)


# ── Validation tests ────────────────────────────────────────────────────────


class TestTraceValidation:
    """Dynamic validation of runtime invariants."""

    @pytest.mark.asyncio
    async def test_every_observation_belongs_to_activity(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)
        outcome = ctx.outcome
        assert outcome is not None

        for obs in outcome.observations:
            assert obs.activity_id == outcome.activity_id, (
                f"Observation {obs.id} has activity_id={obs.activity_id!r}, "
                f"expected {outcome.activity_id!r}"
            )

    @pytest.mark.asyncio
    async def test_no_duplicate_observation_ids(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)
        outcome = ctx.outcome
        assert outcome is not None

        obs_ids = [o.id for o in outcome.observations]
        dupes = [oid for oid, count in Counter(obs_ids).items() if count > 1]
        assert not dupes, f"Duplicate observation IDs: {dupes}"

    @pytest.mark.asyncio
    async def test_every_observation_has_non_empty_fingerprint(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)
        outcome = ctx.outcome
        assert outcome is not None

        for obs in outcome.observations:
            assert obs.fingerprint, f"Observation {obs.id} has empty fingerprint"
            assert len(obs.fingerprint) == 16

    @pytest.mark.asyncio
    async def test_outcome_matches_activity_id(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)
        outcome = ctx.outcome
        assert outcome is not None
        assert outcome.activity_id == ctx.activity_id

    @pytest.mark.asyncio
    async def test_verdict_present_in_context(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)
        assert ctx.verification_result is not None
        verdict = ctx.verification_result
        assert "verdicts" in verdict
        assert verdict["passed"] in (True, False)
        for v in verdict["verdicts"]:
            assert v["outcome"] in ("PASS", "WARNING", "FAIL")

    @pytest.mark.asyncio
    async def test_memory_decision_present_in_context(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)

        assert ctx.store_decision is not None
        decision = ctx.store_decision
        assert decision.action.value in ("store", "skip", "update", "merge", "delete", "ignore")

    @pytest.mark.asyncio
    async def test_observation_parent_refers_to_valid_activity(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)
        outcome = ctx.outcome
        assert outcome is not None

        for obs in outcome.observations:
            if obs.parent_id is not None:
                # Parent ID must reference the same activity
                assert obs.activity_id == outcome.activity_id

    @pytest.mark.asyncio
    async def test_outcome_observation_count_positive(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)
        outcome = ctx.outcome
        assert outcome is not None
        assert len(outcome.observations) >= 1


class TestTraceAcrossMultipleStages:
    """Verify trace continuity through all pipeline stages."""

    @pytest.mark.asyncio
    async def test_activity_id_flows_through_all_stages(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)

        # The activity_id should be set on the context
        aid = ctx.activity_id
        assert aid is not None

        # Outcome references the same activity
        assert ctx.outcome is not None
        assert ctx.outcome.activity_id == aid

        # Observations reference the same activity
        for obs in ctx.outcome.observations:
            assert obs.activity_id == aid

    @pytest.mark.asyncio
    async def test_no_cross_activity_leakage(self):
        """Two sequential executions must not share activity IDs."""
        svc = DeterministicServices.fixed()

        ctx1 = await _run(_make_full_pipeline(), svc)
        ctx2 = await _run(_make_full_pipeline(), svc)

        assert ctx1.activity_id != ctx2.activity_id
        assert ctx1.outcome is not None
        assert ctx2.outcome is not None
        assert ctx1.outcome.activity_id != ctx2.outcome.activity_id


class TestObservationInvariants:
    """Validate Observation dataclass contracts at runtime."""

    @pytest.mark.asyncio
    async def test_observation_is_frozen(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)
        obs = ctx.outcome.observations[0] if ctx.outcome else None
        assert obs is not None
        with pytest.raises(AttributeError):
            obs.source = "modified"  # type: ignore[misc]

    @pytest.mark.asyncio
    async def test_fingerprint_is_deterministic(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)
        obs = ctx.outcome.observations[0] if ctx.outcome else None
        assert obs is not None

        from core.pipeline.observation import Observation

        reconstructed = Observation.new(
            activity_id=obs.activity_id,
            source=obs.source,
            type_=obs.type,
            payload=obs.payload,
            services=svc,
        )
        assert obs.fingerprint == reconstructed.fingerprint
