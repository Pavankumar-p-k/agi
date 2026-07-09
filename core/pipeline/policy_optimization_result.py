"""Frozen contract for the Policy Optimization stage output.

``PolicyOptimizationResult`` is the canonical artifact produced by the
Policy Optimization stage (Sprint 6), consuming ``LearningRecord`` from
the Learning stage and producing optimization signals for downstream
policy decision points (rate limits, capability filtering, profile
selection).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PolicyOptimizationResult:
    """Canonical output of the Policy Optimization stage.

    Analyzes learning records to produce policy optimization signals
    that adjust rate limits, capability filtering, and policy profiles
    for subsequent requests.
    """

    optimization_id: str
    """Unique identifier for this optimization pass."""

    activity_id: str
    """Activity graph node id this optimization is attached to."""

    suggested_profile: str | None = None
    """Suggested ``PolicyProfile`` (``"strict"``, ``"developer"``,
    ``"autonomous"``, or ``None`` for no change)."""

    rate_limit_multiplier: float = 1.0
    """Multiplier applied to the base rate limit (1.0 = no change,
    0.5 = halve, 2.0 = double)."""

    adjusted_risk_max: str | None = None
    """Suggested max ``RiskLevel`` (``"low"``, ``"medium"``,
    ``"high"``, ``"critical"``, or ``None`` for no change)."""

    allow_patterns: tuple[str, ...] = ()
    """Patterns that should bypass confirmations."""

    block_patterns: tuple[str, ...] = ()
    """Patterns that should be blocked."""

    confidence: float = 0.0
    """Confidence in these optimization suggestions (0–1)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extensible bag for stage-specific metadata."""
