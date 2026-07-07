"""Canonical Request Processing Pipeline.

Every request flows through a single pipeline of ordered stages.
Transports are thin adapters that call :func:`process_message`.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.decision import Decision
from core.pipeline.messages import Request, Response
from core.pipeline.observation import Observation
from core.pipeline.outcome import Outcome
from core.pipeline.store_decision import StoreAction, StoreDecision
from core.pipeline.pipeline import Pipeline, get_pipeline, process_message, set_pipeline
from core.pipeline.stages import DEFAULT_STAGES
from core.pipeline.stages.execution import (
    ExecutionStage,
    LiteLLMProvider,
    OllamaFallbackProvider,
    Provider,
    ProviderManager,
    ProviderResult,
)
from core.pipeline.stream import StreamEvent, StreamEventType, stream_pipeline

__all__ = [
    "DEFAULT_STAGES",
    "Decision",
    "ExecutionStage",
    "LiteLLMProvider",
    "Observation",
    "OllamaFallbackProvider",
    "Outcome",
    "Pipeline",
    "PipelineContext",
    "PipelineStage",
    "Provider",
    "ProviderManager",
    "ProviderResult",
    "Request",
    "Response",
    "StageOutcome",
    "StageResult",
    "StreamEvent",
    "StreamEventType",
    "get_pipeline",
    "process_message",
    "set_pipeline",
    "StoreAction",
    "StoreDecision",
    "stream_pipeline",
]
