"""Reasoning stage — canonical intelligence entry point.

Wraps the existing ``core/research/`` engines (ReasoningEngine,
FactReasoner, EvidenceTracker) behind a pipeline-compatible adapter.
Contains almost no business logic — all reasoning lives in the
wrapped engines.
"""
from __future__ import annotations

from core.pipeline.stages.reasoning.stage import ReasoningStage

__all__ = [
    "ReasoningStage",
]
