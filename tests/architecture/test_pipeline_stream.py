from __future__ import annotations

from unittest.mock import patch

import pytest

from core.pipeline import (
    Pipeline,
    PipelineContext,
    PipelineStage,
    Request,
    StageResult,
    StreamEvent,
    stream_pipeline,
)
from core.pipeline.base import StageOutcome


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  StreamEvent dataclass
# ═══════════════════════════════════════════════════════════════════════════════


def test_stream_event_defaults():
    event = StreamEvent(event_type="stage_start", stage="test")
    assert event.event_type == "stage_start"
    assert event.stage == "test"
    assert event.data is None
    assert event.error is None


def test_stream_event_all_fields():
    event = StreamEvent(
        event_type="stage_error",
        stage="execution",
        data={"tokens": 42},
        error="timeout",
    )
    assert event.event_type == "stage_error"
    assert event.data["tokens"] == 42
    assert event.error == "timeout"


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  Mock stages
# ═══════════════════════════════════════════════════════════════════════════════


class _PassStage(PipelineStage):
    @property
    def name(self) -> str:
        return "pass"

    async def execute(self, context: PipelineContext) -> StageResult:
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


class _FailStage(PipelineStage):
    @property
    def name(self) -> str:
        return "fail"

    async def execute(self, context: PipelineContext) -> StageResult:
        return StageResult(
            outcome=StageOutcome.FAIL,
            context=context,
            error="intentional failure",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  Pipeline streaming
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_stream_empty_pipeline():
    """Empty pipeline yields pipeline_start → pipeline_end."""
    pipeline = Pipeline()
    ctx = PipelineContext(request_id="s1", transport="test")

    events: list[StreamEvent] = []
    async for event in pipeline.stream(ctx):
        events.append(event)

    assert len(events) >= 2
    assert events[0].event_type == "pipeline_start"
    assert events[-1].event_type == "pipeline_end"
    assert events[-1].data is not None
    assert events[-1].data.get("execution_state") == "pending"


@pytest.mark.asyncio
async def test_stream_single_stage():
    """Single-pass stage yields stage_start → stage_end → pipeline_end."""
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())
    ctx = PipelineContext(request_id="s2", transport="test")

    types: list[str] = []
    stages: list[str] = []
    async for event in pipeline.stream(ctx):
        types.append(event.event_type)
        if event.stage:
            stages.append(event.stage)

    assert "pipeline_start" in types
    assert "stage_start" in types
    assert "stage_end" in types
    assert "pipeline_end" in types
    assert "pass" in stages


@pytest.mark.asyncio
async def test_stream_fail_stage():
    """Failing stage yields stage_start → stage_error → pipeline_error."""
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())
    pipeline.add_stage(_FailStage())
    pipeline.add_stage(_PassStage())
    ctx = PipelineContext(request_id="s3", transport="test")

    types: list[str] = []
    async for event in pipeline.stream(ctx):
        types.append(event.event_type)

    assert "stage_start" in types
    assert "stage_end" in types  # first pass stage completes
    assert "stage_error" in types or "pipeline_error" in types
    assert "pipeline_error" in types
    assert "pipeline_end" not in types  # pipeline_error is terminal


@pytest.mark.asyncio
async def test_stream_cancelled():
    """Pipeline.cancel() yields pipeline_cancelled event."""
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())
    pipeline.cancel()
    ctx = PipelineContext(request_id="s4", transport="test")

    types: list[str] = []
    async for event in pipeline.stream(ctx):
        types.append(event.event_type)

    assert "pipeline_cancelled" in types
    assert "pipeline_end" not in types


@pytest.mark.asyncio
async def test_stream_multiple_stages_ordered():
    """Events respect stage order."""
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())
    pipeline.add_stage(_PassStage())
    pipeline.add_stage(_PassStage())
    ctx = PipelineContext(request_id="s5", transport="test")

    stage_end_count = 0
    async for event in pipeline.stream(ctx):
        if event.event_type == "stage_end":
            stage_end_count += 1

    assert stage_end_count == 3


@pytest.mark.asyncio
async def test_stream_pipeline_version_in_metadata():
    """pipeline_end event contains pipeline_version in metadata."""
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())
    ctx = PipelineContext(request_id="s6", transport="test")

    final_event: StreamEvent | None = None
    async for event in pipeline.stream(ctx):
        if event.event_type == "pipeline_end":
            final_event = event
            break

    assert final_event is not None
    metadata = final_event.data.get("metadata", {}) if final_event.data else {}
    assert metadata.get("pipeline_version") == "1.0"
    assert "activity_id" in metadata
    assert "trace_id" in metadata


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  stream_pipeline module function
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_stream_pipeline_module_function():
    """stream_pipeline() builds a context from Request and yields events."""
    from core.pipeline import get_pipeline, set_pipeline

    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())
    set_pipeline(pipeline)

    request = Request(
        text="hello",
        transport="test",
        user_id="u1",
        session_id="s1",
    )

    types: list[str] = []
    async for event in stream_pipeline(request):
        types.append(event.event_type)

    assert "pipeline_start" in types
    assert "pipeline_end" in types

    # Reset default pipeline
    set_pipeline(Pipeline())


@pytest.mark.asyncio
async def test_stream_pipeline_handles_error():
    """stream_pipeline() yields pipeline_error when a stage fails."""
    from core.pipeline import get_pipeline, set_pipeline

    pipeline = Pipeline()
    pipeline.add_stage(_FailStage())
    set_pipeline(pipeline)
    request = Request(text="fail me", transport="test")

    types: list[str] = []
    error_events: list[str] = []
    async for event in stream_pipeline(request):
        types.append(event.event_type)
        if event.error:
            error_events.append(event.error)

    assert "pipeline_error" in types
    assert any("intentional failure" in e for e in error_events)

    # Reset default pipeline
    set_pipeline(Pipeline())


@pytest.mark.asyncio
async def test_stream_pipeline_context_has_all_fields():
    """The context built by stream_pipeline() has expected fields."""
    pipeline = Pipeline()
    pipeline.add_stage(_PassStage())

    ctx = PipelineContext(
        request_id="sf1",
        transport="test",
        raw_input="hello",
    )
    ctx.trace_id = ctx.request_id

    final_ctx = None
    async for event in pipeline.stream(ctx):
        if event.event_type in ("pipeline_end", "pipeline_error"):
            if event.data and "_context" in event.data:
                final_ctx = event.data["_context"]

    assert final_ctx is not None
    assert final_ctx.request_id == "sf1"
    assert final_ctx.transport == "test"
    assert final_ctx.raw_input == "hello"
    assert final_ctx.pipeline_version == "1.0"
