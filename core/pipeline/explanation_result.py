"""Frozen contract for the Explainability stage output.

``ExplanationResult`` is the canonical artifact produced by the
Explainability stage (Sprint 7), consumed by the Formatter stage
to enrich the final response with an explanation of the system's
reasoning, decision chain, and confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExplanationResult:
    """Canonical output of the Explainability stage.

    Wraps the full decision chain of the pipeline into a structured
    explanation that the Formatter stage can render as a human-readable
    narrative or structured debug output.
    """

    explanation_id: str
    """Unique identifier for this explanation pass."""

    request_id: str
    """Links back to the original request."""

    summary: str
    """High-level human-readable explanation of what happened
    and why."""

    confidence: float = 0.0
    """Overall confidence in the explanation and the decisions
    it describes (0–1)."""

    reasoning_trace: tuple[str, ...] = ()
    """Ordered steps the system took (e.g. intent classification
    -> reasoning -> planning -> execution -> reflection)."""

    key_findings: tuple[str, ...] = ()
    """Most important facts, conclusions, or outcomes."""

    contradictions: tuple[str, ...] = ()
    """Conflicting information detected during processing."""

    knowledge_sources: tuple[str, ...] = ()
    """Sources consulted during knowledge retrieval."""

    reasoning_detail: dict[str, Any] = field(default_factory=dict)
    """Optional structured dump of ReasoningResult data."""

    plan_detail: dict[str, Any] = field(default_factory=dict)
    """Optional structured dump of the plan that was executed."""

    reflection_detail: dict[str, Any] = field(default_factory=dict)
    """Optional structured dump of ReflectionResult data."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extensible bag for stage-specific metadata."""
