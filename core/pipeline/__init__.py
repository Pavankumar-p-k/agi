"""Canonical Request Processing Pipeline.

Every request flows through a single pipeline of ordered stages.
Transports are thin adapters that call ``process_message()``.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.pipeline import Pipeline

__all__ = [
    "Pipeline",
    "PipelineContext",
    "PipelineStage",
    "StageOutcome",
    "StageResult",
]
