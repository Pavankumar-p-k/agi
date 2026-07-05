"""Canonical Request Processing Pipeline.

Every request flows through a single pipeline of ordered stages.
Transports are thin adapters that call :func:`process_message`.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.messages import Request, Response
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

__all__ = [
    "DEFAULT_STAGES",
    "ExecutionStage",
    "LiteLLMProvider",
    "OllamaFallbackProvider",
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
    "get_pipeline",
    "process_message",
    "set_pipeline",
]
