"""Compatibility shim for the reasoning stage (audit Rule 6).

The implementation lives in ``core/pipeline/stages/reasoning/stage.py``,
which is the only module allowed to construct a ``ReasoningResult``
(Rule 48). This module keeps the historical import path working.
"""
from __future__ import annotations

from core.pipeline.stages.reasoning.stage import ReasonerStage, ReasoningStage

__all__ = ["ReasonerStage", "ReasoningStage"]
