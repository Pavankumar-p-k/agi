"""Planner stage — multi-strategy plan generation.

Wraps the existing ``core/research/planner.py`` ResearchPlanner as
one strategy generator among many (direct, research-driven, code-first,
etc.).
"""
from __future__ import annotations

from core.pipeline.stages.planner.stage import PlannerStage

__all__ = [
    "PlannerStage",
]
