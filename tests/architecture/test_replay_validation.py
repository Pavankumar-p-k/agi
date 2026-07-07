"""Sprint 5.5B — Replay Validation.

Records a Request → Pipeline → Outcome execution, then replays with the
same deterministic services and mocked provider.  Asserts structural
identity of all architecture artifacts.
"""
from __future__ import annotations

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
