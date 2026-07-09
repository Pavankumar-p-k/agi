"""Frozen contract for the Reflection stage output.

``ReflectionResult`` is the canonical artifact produced by the
Reflection stage, consumed by the Learning stage (Sprint 5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReflectionResult:
    """Canonical output of the Reflection stage.

    Wraps the existing ``core/research/reflection.py::ReflectionResult``
    into a pipeline-frozen contract.  Every downstream stage (Learning)
    reads from this artifact.
    """

    reflection_id: str
    """Unique identifier for this reflection pass."""

    activity_id: str
    """Activity graph node id this reflection is attached to."""

    question: str
    """Original request question."""

    strategies_used: tuple[str, ...] = ()
    """Strategies detected in the completed activity."""

    total_facts_collected: int = 0
    """Number of facts collected during the activity."""

    total_sources: int = 0
    """Number of sources consulted."""

    goals_answered: int = 0
    """Number of goals that were answered."""

    goals_total: int = 0
    """Total number of goals defined."""

    contradictions_found: int = 0
    """Number of contradictions detected."""

    overall_confidence: float = 0.0
    """Overall confidence score (0–1)."""

    iterations_needed: int = 1
    """Number of research iterations performed."""

    success_rating: float = 0.0
    """How successful the activity was (0–1)."""

    lessons: tuple[str, ...] = ()
    """Lessons learned from this activity."""

    patterns: tuple[str, ...] = ()
    """Reusable patterns extracted."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extensible bag for stage-specific metadata."""
