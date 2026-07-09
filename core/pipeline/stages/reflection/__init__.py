"""Reflection stage — canonical post-execution analysis.

Wraps the existing ``core/research/reflection.py`` ResearchReflection
engine behind a pipeline-compatible adapter.
"""
from __future__ import annotations

from core.pipeline.stages.reflection.stage import ReflectionStage

__all__ = [
    "ReflectionStage",
]
