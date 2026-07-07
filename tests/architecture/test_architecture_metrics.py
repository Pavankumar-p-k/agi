"""Sprint 5.5D — Architecture Metrics + Snapshot Tests.

Validates per-request architecture metrics are populated after pipeline
execution and that the full execution trace can be serialized as a JSON
snapshot for regression detection.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.pipeline.architecture_metrics import ArchitectureMetrics
from core.pipeline.context import PipelineContext
from core.pipeline.deterministic import DeterministicServices
from core.pipeline.pipeline import Pipeline
from core.pipeline.stages.execution import (
    ExecutionStage,
    Provider,
    ProviderResult,
)
from core.pipeline.stages.verification import VerificationStage
from core.pipeline.stages.memory import MemoryStage


# ── Fake provider ───────────────────────────────────────────────────────────


class FakeProvider(Provider):
    def __init__(self, text: str = "response"):
        self._text = text

    @property
    def name(self) -> str:
        return "fake"

    async def complete(self, prompt: str, **kwargs) -> ProviderResult:
        return ProviderResult(text=self._text, provider="fake", tokens=0)


# ── Helper ──────────────────────────────────────────────────────────────────


def _make_full_pipeline() -> Pipeline:
    stage = ExecutionStage()
    stage.provider_manager.add_provider(FakeProvider("metrics test"))
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


# ── Architecture Metrics Tests ──────────────────────────────────────────────


class TestArchitectureMetricsDataclass:
    def test_defaults(self):
        m = ArchitectureMetrics()
        assert m.reasoning_complexity == "unknown"
        assert m.plan_steps == 0
        assert m.observations == 0
        assert m.execution_state == "pending"

    def test_to_dict(self):
        m = ArchitectureMetrics(
            reasoning_complexity="simple",
            plan_steps=3,
            observations=5,
        )
        d = m.to_dict()
        assert d["reasoning_complexity"] == "simple"
        assert d["plan_steps"] == 3
        assert d["observations"] == 5
        assert "execution_state" in d

    def test_to_dict_roundtrip(self):
        m = ArchitectureMetrics(
            reasoning_complexity="multi_step",
            plan_steps=4,
            selected_capabilities=3,
            observations=6,
            verifiers=4,
            memory_operations=2,
            activity_depth=5,
            retries=1,
            execution_state="completed",
        )
        d = m.to_dict()
        restored = ArchitectureMetrics(**d)
        assert restored == m


class TestArchitectureMetricsPipeline:
    @pytest.mark.asyncio
    async def test_metrics_populated_after_pipeline(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)

        m = ctx.architecture_metrics
        assert m.execution_state == "completed"
        assert m.observations >= 1
        assert m.verifiers >= 1

    @pytest.mark.asyncio
    async def test_metrics_with_plan(self):
        svc = DeterministicServices.fixed()
        plan = {
            "goal": "test",
            "steps": [
                {"intent": "respond", "objective": "step 1"},
                {"intent": "respond", "objective": "step 2"},
            ],
        }
        ctx = PipelineContext(
            raw_input="hello",
            request_id=svc.uuid4(),
            transport="test",
            services=svc,
            plan=plan,
            selected_capabilities={0: [], 1: []},
        )
        ctx.activity_id = ctx.request_id
        p = _make_full_pipeline()
        ctx = await p.execute(ctx)

        m = ctx.architecture_metrics
        assert m.plan_steps == 2
        assert m.selected_capabilities == 2
        assert m.execution_state == "completed"

    @pytest.mark.asyncio
    async def test_metrics_memory_operations(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)
        assert ctx.architecture_metrics.memory_operations >= 1

    @pytest.mark.asyncio
    async def test_metrics_reasoning_complexity_default(self):
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)
        # No ReasonerStage in this pipeline, so complexity is "unknown"
        assert ctx.architecture_metrics.reasoning_complexity == "unknown"


# ── Snapshot Tests ──────────────────────────────────────────────────────────


SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_FILE = SNAPSHOT_DIR / "basic_trace.json"


class TestSnapshotSerialization:
    """Serialize full pipeline execution trace to JSON and compare."""

    @pytest.mark.asyncio
    async def test_snapshot_serialization(self):
        """Produce a JSON snapshot of the full execution trace."""
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)

        trace = _build_trace(ctx)
        snapshot = json.dumps(trace, indent=2, default=str, sort_keys=True)
        assert len(snapshot) > 50
        # Validate it can be parsed back
        parsed = json.loads(snapshot)
        assert parsed["activity_id"] == ctx.activity_id
        assert "outcome" in parsed
        assert "observations" in parsed["outcome"]

    @pytest.mark.asyncio
    async def test_snapshot_basic_structure(self):
        """Validate the shape of the snapshot."""
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)

        trace = _build_trace(ctx)
        _validate_trace_structure(trace)

    @pytest.mark.asyncio
    async def test_snapshot_file_written_and_readable(self):
        """Write a snapshot file and verify it can be read back."""
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        svc = DeterministicServices.fixed()
        ctx = await _run(_make_full_pipeline(), svc)

        trace = _build_trace(ctx)
        SNAPSHOT_FILE.write_text(
            json.dumps(trace, indent=2, default=str, sort_keys=True),
            encoding="utf-8",
        )

        loaded = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
        assert loaded["activity_id"] == ctx.activity_id
        assert len(loaded["outcome"]["observations"]) == len(ctx.outcome.observations)

        SNAPSHOT_FILE.unlink(missing_ok=True)


# ── Trace builder ───────────────────────────────────────────────────────────


def _build_trace(ctx: PipelineContext) -> dict:
    outcome = ctx.outcome
    return {
        "activity_id": ctx.activity_id,
        "request_id": ctx.request_id,
        "execution_state": ctx.execution_state,
        "architecture_metrics": ctx.architecture_metrics.to_dict(),
        "outcome": {
            "activity_id": outcome.activity_id if outcome else None,
            "success": outcome.success if outcome else None,
            "observations": [
                {
                    "id": o.id,
                    "fingerprint": o.fingerprint,
                    "activity_id": o.activity_id,
                    "source": o.source,
                    "type": o.type,
                    "payload": o.payload,
                }
                for o in (outcome.observations if outcome else [])
            ],
        },
        "verification": ctx.verification_result,
        "store_decision": {
            "action": ctx.store_decision.action.value,
            "store_type": ctx.store_decision.store_type,
            "confidence": ctx.store_decision.confidence,
        } if ctx.store_decision else None,
        "pipeline_version": ctx.pipeline_version,
    }


def _validate_trace_structure(trace: dict) -> None:
    """Validate the shape of a trace snapshot."""
    assert "activity_id" in trace
    assert trace["activity_id"] is not None
    assert "request_id" in trace
    assert "execution_state" in trace
    assert "architecture_metrics" in trace
    assert "outcome" in trace
    assert trace["outcome"]["activity_id"] == trace["activity_id"]
    assert len(trace["outcome"]["observations"]) > 0
    for obs in trace["outcome"]["observations"]:
        assert obs["activity_id"] == trace["activity_id"]
        assert "fingerprint" in obs
        assert "id" in obs
    assert "verification" in trace
    assert "store_decision" in trace
    assert trace["store_decision"]["action"] in ("store", "skip", "update", "merge", "delete", "ignore")
    assert "pipeline_version" in trace
