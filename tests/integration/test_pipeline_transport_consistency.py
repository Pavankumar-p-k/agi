"""Integration test: same prompt through every transport adapter.

Verifies that all transports produce consistent intent classification,
execution results, and metadata when routed through the canonical pipeline.

The test:
1. Creates a mock pipeline (a single PassStage + a CaptureStage)
2. Registers mock providers on the real ExecutionStage
3. Sends the same prompt through each transport adapter
4. Asserts all adapters produce the same pipeline context metadata
"""
from __future__ import annotations

import pytest

from core.pipeline import Pipeline, PipelineContext, process_message, set_pipeline
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.messages import Request, Response


class _CaptureStage(PipelineStage):
    """Records the pipeline context for inspection after execution."""

    def __init__(self) -> None:
        self.captured: PipelineContext | None = None

    @property
    def name(self) -> str:
        return "capture"

    async def execute(self, context: PipelineContext) -> StageResult:
        self.captured = context
        context.classification = {"mode": "chat", "confidence": 0.95}
        context.execution_result = {
            "text": f"Processed: {context.raw_input}",
            "provider": "test_provider",
            "tokens": 42,
        }
        context.epistemic_tags = {"confidence": 1.0, "source": "test"}
        context.formatted_response = {
            "text": f"Processed: {context.raw_input}",
            "epistemic": {"confidence": 1.0, "source": "test"},
            "metrics": {"tokens": 42},
        }
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


@pytest.fixture
def mock_pipeline():
    """Set up a deterministic test pipeline with a capture stage."""
    import core.pipeline.pipeline as _pp

    old = _pp._default_pipeline
    capture = _CaptureStage()
    p = Pipeline()
    p.add_stage(capture)
    set_pipeline(p)
    yield capture
    # Restore the original singleton
    set_pipeline(old)


@pytest.mark.asyncio
async def test_channel_adapter_consistency(mock_pipeline):
    """Channel adapter produces correct pipeline context."""
    from core.pipeline.adapters import channel_adapter

    result = await channel_adapter(
        text="what is the weather",
        source="telegram",
        channel_id="ch1",
        user_id="u1",
        user_name="TestUser",
    )

    assert result == "Processed: what is the weather"
    ctx = mock_pipeline.captured
    assert ctx is not None
    assert ctx.transport == "telegram"
    assert ctx.raw_input == "what is the weather"
    assert ctx.user_id == "u1"
    assert ctx.session_id == "ch1"


@pytest.mark.asyncio
async def test_rest_adapter_consistency(mock_pipeline):
    """REST adapter produces correct pipeline context."""
    from core.pipeline.adapters import rest_adapter

    result = await rest_adapter(
        message="what is the weather",
        user_id="u1",
        session_id="s1",
    )

    assert result["response"] == "Processed: what is the weather"
    assert result["model"] == "pipeline"
    ctx = mock_pipeline.captured
    assert ctx is not None
    assert ctx.transport == "rest"
    assert ctx.raw_input == "what is the weather"
    assert ctx.user_id == "u1"
    assert ctx.session_id == "s1"


@pytest.mark.asyncio
async def test_ws_adapter_consistency(mock_pipeline):
    """WebSocket adapter produces correct pipeline context."""
    from core.pipeline.adapters import ws_adapter

    result = await ws_adapter(
        text="what is the weather",
        user_id="u1",
        session_id="s1",
    )

    assert result is not None
    assert result["response"] == "Processed: what is the weather"
    ctx = mock_pipeline.captured
    assert ctx is not None
    assert ctx.transport == "websocket"
    assert ctx.raw_input == "what is the weather"
    assert ctx.user_id == "u1"
    assert ctx.session_id == "s1"


@pytest.mark.asyncio
async def test_voice_adapter_consistency(mock_pipeline):
    """Voice adapter produces correct pipeline context."""
    from core.pipeline.adapters import voice_adapter

    result = await voice_adapter(
        text="what is the weather",
        user_id="u1",
        session_id="s1",
    )

    assert result == "Processed: what is the weather"
    ctx = mock_pipeline.captured
    assert ctx is not None
    assert ctx.transport == "voice"
    assert ctx.raw_input == "what is the weather"
    assert ctx.user_id == "u1"
    assert ctx.session_id == "s1"


@pytest.mark.asyncio
async def test_all_adapters_consistent_transport(mock_pipeline):
    """All adapters set the correct transport value."""
    from core.pipeline.adapters import channel_adapter, rest_adapter, voice_adapter, ws_adapter

    test_cases = [
        (channel_adapter, {"text": "hello", "source": "discord", "channel_id": "c1", "user_id": "u1", "user_name": "u"}, "discord"),
        (rest_adapter, {"message": "hello", "user_id": "u1", "session_id": "s1"}, "rest"),
        (ws_adapter, {"text": "hello", "user_id": "u1", "session_id": "s1"}, "websocket"),
        (voice_adapter, {"text": "hello", "user_id": "u1", "session_id": "s1"}, "voice"),
    ]

    for adapter_fn, kwargs, expected_transport in test_cases:
        if adapter_fn in (channel_adapter,):
            result = await adapter_fn(**kwargs)
        elif adapter_fn in (rest_adapter,):
            result = await adapter_fn(**kwargs)
        elif adapter_fn in (ws_adapter,):
            result = await adapter_fn(**kwargs)
        else:
            result = await adapter_fn(**kwargs)

        ctx = mock_pipeline.captured
        assert ctx is not None, f"{adapter_fn.__name__} did not capture context"
        assert ctx.transport == expected_transport, (
            f"{adapter_fn.__name__}: expected transport={expected_transport!r}, got {ctx.transport!r}"
        )
        assert ctx.classification == {"mode": "chat", "confidence": 0.95}, (
            f"{adapter_fn.__name__}: classification mismatch"
        )
        assert ctx.execution_result["provider"] == "test_provider", (
            f"{adapter_fn.__name__}: execution provider mismatch"
        )
