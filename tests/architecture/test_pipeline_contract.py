"""Architecture tests for the canonical request processing pipeline.

Phase 2A — Contract definition.  These tests verify that the pipeline
interfaces, context, and runner exist and behave as specified by ADR-006.
"""
from __future__ import annotations

import pytest

from core.pipeline import (
    Pipeline,
    PipelineContext,
    PipelineStage,
    Request,
    Response,
    StageResult,
    get_pipeline,
    process_message,
    set_pipeline,
)
from core.pipeline.base import StageOutcome  # noqa: I001 — ruff doesn't merge this

# ═══════════════════════════════════════════════════════════════════════════════
# 1.  Interfaces exist
# ═══════════════════════════════════════════════════════════════════════════════


def test_stage_outcome_has_enum_values():
    assert StageOutcome.CONTINUE.value == "continue"
    assert StageOutcome.SHORT_CIRCUIT.value == "short_circuit"
    assert StageOutcome.RETRY.value == "retry"
    assert StageOutcome.FAIL.value == "fail"
    assert StageOutcome.DEFER.value == "defer"


def test_stage_result_is_dataclass():
    ctx = PipelineContext(request_id="r1", transport="test")
    result = StageResult(outcome=StageOutcome.CONTINUE, context=ctx)
    assert result.outcome == StageOutcome.CONTINUE
    assert result.context is ctx
    assert result.error is None
    assert result.retry_count == 0
    assert result.metrics == {}


def test_stage_result_accepts_optional_fields():
    ctx = PipelineContext(request_id="r1", transport="test")
    result = StageResult(
        outcome=StageOutcome.FAIL,
        context=ctx,
        error="something broke",
        retry_count=0,
        metrics={"tokens": 42},
    )
    assert result.error == "something broke"
    assert result.metrics["tokens"] == 42


def test_pipeline_stage_is_abstract():
    """Can't instantiate PipelineStage directly — must subclass."""
    with pytest.raises(TypeError):
        PipelineStage()  # type: ignore[abstract]


def test_pipeline_context_requires_request_id_and_transport():
    ctx = PipelineContext(request_id="r1", transport="test")
    assert ctx.request_id == "r1"
    assert ctx.transport == "test"
    assert ctx.user_id is None
    assert ctx.execution_state == "pending"


def test_pipeline_context_has_all_expected_fields():
    """Snapshot test for the context schema."""
    ctx = PipelineContext(request_id="r1", transport="test")
    assert hasattr(ctx, "request_id")
    assert hasattr(ctx, "transport")
    assert hasattr(ctx, "user_id")
    assert hasattr(ctx, "session_id")
    assert hasattr(ctx, "raw_input")
    assert hasattr(ctx, "parsed_request")
    assert hasattr(ctx, "classification")
    assert hasattr(ctx, "selected_capabilities")
    assert hasattr(ctx, "plan")
    assert hasattr(ctx, "execution_state")
    assert hasattr(ctx, "execution_result")
    assert hasattr(ctx, "verification_result")
    assert hasattr(ctx, "epistemic_tags")
    assert hasattr(ctx, "memory_refs")
    assert hasattr(ctx, "activity_id")
    assert hasattr(ctx, "trace_id")
    assert hasattr(ctx, "span_stack")
    assert hasattr(ctx, "formatted_response")
    assert hasattr(ctx, "metrics")
    assert hasattr(ctx, "metadata")
    assert hasattr(ctx, "attachments")
    assert hasattr(ctx, "messages")
    assert hasattr(ctx, "error")


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  Request / Response types
# ═══════════════════════════════════════════════════════════════════════════════


def test_request_required_fields():
    req = Request(text="hello", transport="rest")
    assert req.text == "hello"
    assert req.transport == "rest"
    assert req.user_id is None
    assert req.attachments == []
    assert req.metadata == {}


def test_request_with_optional_fields():
    req = Request(
        text="hello",
        transport="telegram",
        user_id="u1",
        session_id="s1",
        attachments=[{"name": "photo.jpg"}],
        metadata={"chat_id": 42},
    )
    assert req.user_id == "u1"
    assert req.metadata["chat_id"] == 42


def test_response_required_fields():
    resp = Response(text="hi there")
    assert resp.text == "hi there"
    assert resp.error is None
    assert resp.data is None
    assert resp.metadata == {}


def test_response_with_error():
    resp = Response(text="", error="something broke", metadata={"tokens": 10})
    assert resp.error == "something broke"
    assert resp.metadata["tokens"] == 10


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  process_message()
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_process_message_function_exists():
    """The module-level process_message() is callable and returns a Response."""
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())
    set_pipeline(pipeline)

    resp = await process_message(Request(text="hello", transport="pytest"))
    assert isinstance(resp, Response)
    assert resp.error is None


@pytest.mark.asyncio
async def test_process_message_with_formatter():
    """A stage that sets formatted_response produces a Response with text."""
    class _FormatterStage(PipelineStage):
        @property
        def name(self) -> str:
            return "formatter"

        async def execute(self, context: PipelineContext) -> StageResult:
            context.formatted_response = {"text": "formatted: " + context.raw_input}
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    pipeline = Pipeline()
    pipeline.add_stage(_PassStage()).add_stage(_FormatterStage())
    set_pipeline(pipeline)

    resp = await process_message(Request(text="world", transport="pytest"))
    assert resp.text == "formatted: world"


@pytest.mark.asyncio
async def test_process_message_with_error():
    """A stage that fails produces a Response with error set."""
    pipeline = Pipeline()
    pipeline.add_stage(_FailStage())
    set_pipeline(pipeline)

    resp = await process_message(Request(text="hello", transport="pytest"))
    assert resp.error == "intentional failure"


@pytest.mark.asyncio
async def test_get_pipeline_returns_singleton():
    p1 = get_pipeline()
    p2 = get_pipeline()
    assert p1 is p2


@pytest.mark.asyncio
async def test_set_pipeline_overrides_default():
    p = Pipeline()
    set_pipeline(p)
    assert get_pipeline() is p


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  Pipeline runner
# ═══════════════════════════════════════════════════════════════════════════════


class _PassStage(PipelineStage):
    """Stage that always returns CONTINUE."""

    @property
    def name(self) -> str:
        return "pass"

    async def execute(self, context: PipelineContext) -> StageResult:
        context.metadata["pass_ran"] = True
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


class _FailStage(PipelineStage):
    """Stage that returns FAIL."""

    @property
    def name(self) -> str:
        return "fail"

    async def execute(self, context: PipelineContext) -> StageResult:
        return StageResult(
            outcome=StageOutcome.FAIL,
            context=context,
            error="intentional failure",
        )


class _ShortCircuitStage(PipelineStage):
    """Stage that returns SHORT_CIRCUIT."""

    @property
    def name(self) -> str:
        return "short_circuit"

    async def execute(self, context: PipelineContext) -> StageResult:
        return StageResult(
            outcome=StageOutcome.SHORT_CIRCUIT,
            context=context,
            error="intentional short-circuit",
        )


class _DeferStage(PipelineStage):
    """Stage that returns DEFER."""

    @property
    def name(self) -> str:
        return "defer"

    async def execute(self, context: PipelineContext) -> StageResult:
        return StageResult(
            outcome=StageOutcome.DEFER,
            context=context,
            error="needs user input",
        )


class _MetricsStage(PipelineStage):
    """Stage that emits metrics."""

    @property
    def name(self) -> str:
        return "metrics"

    async def execute(self, context: PipelineContext) -> StageResult:
        return StageResult(
            outcome=StageOutcome.CONTINUE,
            context=context,
            metrics={"tokens": 100, "duration_ms": 5},
        )


@pytest.fixture
def ctx() -> PipelineContext:
    return PipelineContext(request_id="test-1", transport="pytest")


@pytest.mark.asyncio
async def test_empty_pipeline_returns_context(ctx):
    pipeline = Pipeline()
    result = await pipeline.execute(ctx)
    assert result is ctx
    assert result.request_id == "test-1"
    assert result.execution_state == "pending"


@pytest.mark.asyncio
async def test_pipeline_runs_stages_in_order(ctx):
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())
    pipeline.add_stage(_PassStage())

    result = await pipeline.execute(ctx)
    assert result.metadata.get("pass_ran") is True


@pytest.mark.asyncio
async def test_pipeline_stops_on_fail(ctx):
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())
    pipeline.add_stage(_FailStage())
    pipeline.add_stage(_PassStage())  # should NOT run

    result = await pipeline.execute(ctx)
    assert result.execution_state == "failed"


@pytest.mark.asyncio
async def test_pipeline_stops_on_short_circuit(ctx):
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())
    pipeline.add_stage(_ShortCircuitStage())
    pipeline.add_stage(_PassStage())  # should NOT run

    result = await pipeline.execute(ctx)
    assert result.execution_state == "short_circuited"


@pytest.mark.asyncio
async def test_pipeline_stops_on_defer(ctx):
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())
    pipeline.add_stage(_DeferStage())
    pipeline.add_stage(_PassStage())  # should NOT run

    result = await pipeline.execute(ctx)
    assert result.execution_state == "deferred"


@pytest.mark.asyncio
async def test_pipeline_merges_stage_metrics(ctx):
    pipeline = Pipeline()
    pipeline.add_stage(_MetricsStage())

    result = await pipeline.execute(ctx)
    assert "metrics" in result.metrics
    assert result.metrics["metrics"]["tokens"] == 100


@pytest.mark.asyncio
async def test_pipeline_without_context_creates_one():
    pipeline = Pipeline()
    result = await pipeline.execute()
    assert len(result.request_id) == 32  # hex uuid
    assert result.transport == "unknown"


@pytest.mark.asyncio
async def test_process_message_convenience():
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())

    result = await pipeline.process_message(
        "hello",
        "rest",
        user_id="u1",
        session_id="s1",
    )
    assert result.raw_input == "hello"
    assert result.transport == "rest"
    assert result.user_id == "u1"
    assert result.session_id == "s1"
    assert len(result.request_id) == 32


@pytest.mark.asyncio
async def test_stage_registration_fluent():
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage()).add_stage(_PassStage())
    assert len(pipeline.stages) == 2


@pytest.mark.asyncio
async def test_insert_stage():
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage()).add_stage(_PassStage())
    pipeline.insert_stage(1, _FailStage())
    assert len(pipeline.stages) == 3
    assert pipeline.stages[1].name == "fail"


@pytest.mark.asyncio
async def test_remove_stage():
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage()).add_stage(_FailStage())
    assert pipeline.remove_stage("fail") is True
    assert len(pipeline.stages) == 1
    assert pipeline.remove_stage("nonexistent") is False


@pytest.mark.asyncio
async def test_span_stack_tracking(ctx):
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage()).add_stage(_PassStage())
    result = await pipeline.execute(ctx)
    assert result.span_stack == []
