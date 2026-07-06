"""Architecture tests for the canonical request processing pipeline.

Phase 2A — Contract definition.  These tests verify that the pipeline
interfaces, context, and runner exist and behave as specified by ADR-006.
"""
from __future__ import annotations

import asyncio

import pytest

from core.pipeline import (
    DEFAULT_STAGES,
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
from core.pipeline.stages import (
    AuthenticationStage,
    CapabilitySelectionStage,
    ContextRetrievalStage,
    EpistemicTaggingStage,
    FormatterStage,
    IntentStage,
    LoadContextStage,
    MetricsStage,
    PlanValidatorStage,
    PlannerStage,
    ReasonerStage,
    ReceiveStage,
    VerificationStage,
)

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
    assert hasattr(ctx, "retrieved_context")
    assert hasattr(ctx, "reasoning_assessment")
    assert hasattr(ctx, "plan")
    assert hasattr(ctx, "plan_validated")
    assert hasattr(ctx, "selected_capabilities")
    assert hasattr(ctx, "execution_state")
    assert hasattr(ctx, "execution_result")
    assert hasattr(ctx, "verification_result")
    assert hasattr(ctx, "epistemic_tags")
    assert hasattr(ctx, "memory_refs")
    assert hasattr(ctx, "store_decision")
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


# ═══════════════════════════════════════════════════════════════════════════════
# 5.  Stage extraction — default stages exist
# ═══════════════════════════════════════════════════════════════════════════════


def test_default_stages_have_correct_order():
    from core.pipeline import DEFAULT_STAGES

    names = [n for n, _ in DEFAULT_STAGES]
    assert names == [
        "receive",
        "load_context",
        "authentication",
        "rate_limit",
        "intent",
        "context_retrieval",
        "reasoner",
        "planner",
        "plan_validator",
        "capability_selection",
        "execution",
        "verification",
        "epistemic",
        "memory",
        "metrics",
        "formatter",
    ]


def test_all_stage_classes_importable():
    from core.pipeline.stages import (
        AuthenticationStage,
        CapabilitySelectionStage,
        ContextRetrievalStage,
        EpistemicTaggingStage,
        ExecutionStage,
        FormatterStage,
        IntentStage,
        LoadContextStage,
        MemoryStage,
        MetricsStage,
        PlanValidatorStage,
        PlannerStage,
        RateLimitStage,
        ReasonerStage,
        ReceiveStage,
        VerificationStage,
    )
    for cls in (
        AuthenticationStage,
        CapabilitySelectionStage,
        ContextRetrievalStage,
        EpistemicTaggingStage,
        ExecutionStage,
        FormatterStage,
        IntentStage,
        LoadContextStage,
        MemoryStage,
        MetricsStage,
        PlanValidatorStage,
        PlannerStage,
        RateLimitStage,
        ReasonerStage,
        ReceiveStage,
        VerificationStage,
    ):
        obj = cls()
        assert obj.name


def test_default_stage_count():
    """DEFAULT_STAGES has the expected count (ADR-007)."""
    assert len(DEFAULT_STAGES) == 16


@pytest.mark.asyncio
async def test_classify_to_formatter_pipeline():
    """Run from receive through intent to formatter (no Execution).
    Includes all ADR-007 stages."""
    from core.pipeline.stages import (
        ContextRetrievalStage,
        PlanValidatorStage,
        ReasonerStage,
    )

    p = Pipeline()
    for name, cls in (
        ("receive", ReceiveStage),
        ("intent", IntentStage),
        ("context_retrieval", ContextRetrievalStage),
        ("reasoner", ReasonerStage),
        ("planner", PlannerStage),
        ("plan_validator", PlanValidatorStage),
        ("capability_selection", CapabilitySelectionStage),
        ("verification", VerificationStage),
        ("epistemic", EpistemicTaggingStage),
        ("metrics", MetricsStage),
        ("formatter", FormatterStage),
    ):
        p.add_stage(cls())

    ctx = PipelineContext(request_id="test-1", transport="pytest", raw_input="hello world")
    result = await p.execute(ctx)
    assert result.classification is not None
    assert result.classification["mode"] in ("chat", "action", "direct", "codebase", "agent")
    assert result.retrieved_context is not None
    assert result.reasoning_assessment is not None
    assert result.plan is not None
    assert result.plan_validated is True
    assert result.formatted_response is not None
    assert "text" in result.formatted_response


@pytest.mark.asyncio
async def test_receive_stage_parses_input():
    stage = ReceiveStage()
    ctx = PipelineContext(request_id="r1", transport="test", raw_input="hello")
    result = await stage.execute(ctx)
    assert result.outcome == StageOutcome.CONTINUE
    assert result.context.parsed_request == {"text": "hello"}
    assert result.context.parsed_request.get("attachment_count") is None


@pytest.mark.asyncio
async def test_receive_stage_with_attachments():
    stage = ReceiveStage()
    ctx = PipelineContext(
        request_id="r1", transport="test",
        raw_input="hello", attachments=[{"name": "photo.jpg"}],
    )
    result = await stage.execute(ctx)
    assert result.context.parsed_request["attachment_count"] == 1


@pytest.mark.asyncio
async def test_intent_stage_classifies():
    stage = IntentStage()
    ctx = PipelineContext(request_id="r1", transport="test", raw_input="what is the weather")
    result = await stage.execute(ctx)
    assert result.context.classification is not None
    assert "mode" in result.context.classification


@pytest.mark.asyncio
async def test_intent_stage_empty_input():
    stage = IntentStage()
    ctx = PipelineContext(request_id="r1", transport="test", raw_input="")
    result = await stage.execute(ctx)
    assert result.outcome == StageOutcome.CONTINUE


@pytest.mark.asyncio
async def test_formatter_stage_builds_response():
    stage = FormatterStage()
    ctx = PipelineContext(
        request_id="r1", transport="test",
        execution_result={"text": "hello world", "provider": "test", "tokens": 10},
        epistemic_tags={"confidence": 1.0},
        metrics={"tokens": 10},
    )
    result = await stage.execute(ctx)
    assert result.outcome == StageOutcome.CONTINUE
    assert result.context.formatted_response is not None
    assert result.context.formatted_response["text"] == "hello world"
    assert "epistemic" in result.context.formatted_response


@pytest.mark.asyncio
async def test_formatter_stage_with_error():
    stage = FormatterStage()
    ctx = PipelineContext(
        request_id="r1", transport="test",
        error="something broke",
    )
    result = await stage.execute(ctx)
    assert "Error: something broke" in result.context.formatted_response["text"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_load_context_stage_sets_transport(ctx):
    stage = LoadContextStage()
    result = await stage.execute(ctx)
    assert result.context.metadata.get("transport") == "pytest"


@pytest.mark.asyncio
async def test_authentication_stage_pass_through(ctx):
    stage = AuthenticationStage()
    result = await stage.execute(ctx)
    assert result.context.metadata.get("authenticated") is False


@pytest.mark.asyncio
async def test_metrics_stage_aggregates(ctx):
    stage = MetricsStage()
    ctx.classification = {"mode": "chat"}
    ctx.execution_result = {"provider": "test", "tokens": 42}
    result = await stage.execute(ctx)
    assert result.context.metrics.get("intent") == "chat"
    assert result.context.metrics.get("tokens") == 42


@pytest.mark.asyncio
async def test_pipeline_retries_on_retry_outcome():
    """RETRY outcome causes the stage to be re-invoked."""

    call_count = 0

    class _RetryStage(PipelineStage):
        @property
        def name(self) -> str:
            return "retry_stage"

        async def execute(self, context: PipelineContext) -> StageResult:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return StageResult(outcome=StageOutcome.RETRY, context=context)
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    p = Pipeline()
    p.add_stage(_RetryStage())
    ctx = PipelineContext(request_id="r1", transport="test")
    result = await p.execute(ctx)
    assert call_count == 2
    assert result.execution_state == "pending"  # CONTINUE keeps state


@pytest.mark.asyncio
async def test_pipeline_exhausts_retries():
    """Stage that keeps returning RETRY eventually fails."""

    class _AlwaysRetryStage(PipelineStage):
        max_retries = 2

        @property
        def name(self) -> str:
            return "always_retry"

        async def execute(self, context: PipelineContext) -> StageResult:
            return StageResult(
                outcome=StageOutcome.RETRY,
                context=context,
                error="transient error",
            )

    p = Pipeline()
    p.add_stage(_AlwaysRetryStage())
    ctx = PipelineContext(request_id="r1", transport="test")
    result = await p.execute(ctx)
    assert result.execution_state == "failed"
    assert result.error == "stage 'always_retry' exhausted retries: transient error"


@pytest.mark.asyncio
async def test_pipeline_retries_on_timeout():
    """Stage that times out gets retried, then fails."""

    call_count = 0

    class _TimeoutStage(PipelineStage):
        timeout = 0.01
        max_retries = 1

        @property
        def name(self) -> str:
            return "timeout_stage"

        async def execute(self, context: PipelineContext) -> StageResult:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(1)  # much longer than timeout
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    p = Pipeline()
    p.add_stage(_TimeoutStage())
    ctx = PipelineContext(request_id="r1", transport="test")
    result = await p.execute(ctx)
    assert call_count == 2  # initial + 1 retry
    assert result.execution_state == "failed"
    assert "timed out" in (result.error or "")


@pytest.mark.asyncio
async def test_pipeline_retries_on_exception():
    """Stage that raises an exception gets retried, then succeeds."""

    call_count = 0

    class _FickleStage(PipelineStage):
        @property
        def name(self) -> str:
            return "fickle_stage"

        async def execute(self, context: PipelineContext) -> StageResult:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient boom")
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    p = Pipeline()
    p.add_stage(_FickleStage())
    ctx = PipelineContext(request_id="r1", transport="test")
    result = await p.execute(ctx)
    assert call_count == 2
    assert result.execution_state == "pending"


@pytest.mark.asyncio
async def test_pipeline_exception_exhausts_retries():
    """Stage that always raises eventually fails."""

    class _AlwaysCrashStage(PipelineStage):
        max_retries = 1

        @property
        def name(self) -> str:
            return "crash_stage"

        async def execute(self, context: PipelineContext) -> StageResult:
            raise RuntimeError("boom")

    p = Pipeline()
    p.add_stage(_AlwaysCrashStage())
    ctx = PipelineContext(request_id="r1", transport="test")
    result = await p.execute(ctx)
    assert result.execution_state == "failed"
    assert "boom" in (result.error or "")


# ═══════════════════════════════════════════════════════════════════════════════
# 6.  CANCELLED outcome
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pipeline_stops_on_cancelled():
    """CANCELLED outcome from a stage stops the pipeline."""

    class _CancelStage(PipelineStage):
        @property
        def name(self) -> str:
            return "cancel_stage"

        async def execute(self, context: PipelineContext) -> StageResult:
            return StageResult(
                outcome=StageOutcome.CANCELLED,
                context=context,
                error="user interrupted",
            )

    p = Pipeline()
    p.add_stage(_PassStage())
    p.add_stage(_CancelStage())
    p.add_stage(_PassStage())  # should NOT run

    ctx = PipelineContext(request_id="r1", transport="test")
    result = await p.execute(ctx)
    assert result.execution_state == "cancelled"
    assert result.error == "user interrupted"


@pytest.mark.asyncio
async def test_pipeline_external_cancel():
    """Calling pipeline.cancel() mid-execution stops subsequent stages."""

    executed_stages: list[str] = []

    class _TrackStage(PipelineStage):
        def __init__(self, name: str) -> None:
            self._name = name

        @property
        def name(self) -> str:
            return self._name

        async def execute(self, context: PipelineContext) -> StageResult:
            executed_stages.append(self._name)
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    p = Pipeline()
    p.add_stage(_TrackStage("first"))
    p.add_stage(_TrackStage("second"))

    # Cancel before execution
    p.cancel()

    ctx = PipelineContext(request_id="r1", transport="test")
    result = await p.execute(ctx)
    assert result.execution_state == "cancelled"
    assert "first" not in executed_stages


# ═══════════════════════════════════════════════════════════════════════════════
# 7.  Pipeline versioning
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pipeline_version_in_context():
    ctx = PipelineContext(request_id="r1", transport="test")
    assert ctx.pipeline_version == "1.0"


@pytest.mark.asyncio
async def test_process_message_includes_version():
    p = Pipeline()
    p.add_stage(_PassStage())
    set_pipeline(p)

    resp = await process_message(Request(text="hello", transport="pytest"))
    assert resp.metadata.get("pipeline_version") == "1.0"


# ═══════════════════════════════════════════════════════════════════════════════
# 8.  Field ownership
# ═══════════════════════════════════════════════════════════════════════════════


def test_stage_field_ownership_mapping():
    from core.pipeline.base import STAGE_OWNERSHIP

    assert "classification" in STAGE_OWNERSHIP["intent"]
    assert "execution_result" in STAGE_OWNERSHIP["execution"]
    assert "formatted_response" in STAGE_OWNERSHIP["formatter"]
    assert "request_id" not in {f for v in STAGE_OWNERSHIP.values() for f in v}


def test_set_stage_field_ownership_ok():
    ctx = PipelineContext(request_id="r1", transport="test")
    ctx.set_stage_field("intent", "classification", {"mode": "chat"})
    assert ctx.classification == {"mode": "chat"}


# ═══════════════════════════════════════════════════════════════════════════════
# 9.  Lifecycle hooks
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_hooks_fire_before_and_after():
    events: list[str] = []

    def record_before(stage: str, ctx: PipelineContext) -> None:
        events.append(f"before:{stage}")

    def record_after(stage: str, ctx: PipelineContext) -> None:
        events.append(f"after:{stage}")

    p = Pipeline()
    p.hooks.on_before("pass", record_before)
    p.hooks.on_after("pass", record_after)
    p.add_stage(_PassStage())

    ctx = PipelineContext(request_id="r1", transport="test")
    await p.execute(ctx)
    assert "before:pass" in events
    assert "after:pass" in events


@pytest.mark.asyncio
async def test_hook_failure_does_not_crash_pipeline():
    def failing_hook(stage: str, ctx: PipelineContext) -> None:
        raise RuntimeError("hook error")

    p = Pipeline()
    p.hooks.on_before("pass", failing_hook)
    p.add_stage(_PassStage())

    ctx = PipelineContext(request_id="r1", transport="test")
    result = await p.execute(ctx)
    assert result.execution_state == "pending"  # still succeeded


# ═══════════════════════════════════════════════════════════════════════════════
# 10.  Activity ID in response metadata
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_response_includes_activity_metadata():
    p = Pipeline()
    p.add_stage(_PassStage())
    set_pipeline(p)

    resp = await process_message(Request(text="hello", transport="pytest"))
    assert "activity_id" in resp.metadata
    assert "trace_id" in resp.metadata

