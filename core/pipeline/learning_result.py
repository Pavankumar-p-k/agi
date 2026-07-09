"""Frozen contract for the Learning stage output.

``LearningRecord`` is the canonical artifact produced by the
Learning stage (Sprint 5), consuming ``ReflectionResult`` from
the Reflection stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LearningRecord:
    """Canonical output of the Learning stage.

    Consolidates reflection-derived lessons into a structured record
    that the Memory stage persists.  Replaces the legacy
    ``brain/learning_engine.py`` and ``memory/decision_memory.py``
    paths.
    """

    learning_id: str
    """Unique identifier for this learning pass."""

    activity_id: str
    """Activity graph node id this learning is attached to."""

    reflection_id: str
    """ReflectionResult id that generated this learning."""

    success_rating: float = 0.0
    """How successful the activity was (0–1), sourced from Reflection."""

    lessons: tuple[str, ...] = ()
    """Lesson strings extracted from the reflection."""

    patterns: tuple[str, ...] = ()
    """Reusable patterns extracted."""

    strategies_used: tuple[str, ...] = ()
    """Strategies that were used in the activity."""

    total_facts: int = 0
    """Total facts collected during the activity."""

    sources_count: int = 0
    """Number of sources consulted."""

    confidence: float = 0.0
    """Overall confidence from the reflection."""

    contradictions: int = 0
    """Number of contradictions found."""

    store_decision: str = "store"
    """Whether to persist this record: ``"store"`` or ``"skip"``."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extensible bag for stage-specific metadata."""
