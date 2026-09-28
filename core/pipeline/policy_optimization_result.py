"""PolicyOptimizationResult + LearningRecord store-decision artifacts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PolicyOptimizationResult:
    optimization_id: str = ""
    activity_id: str = ""
    suggested_profile: str = "standard"
    rate_limit_multiplier: float = 1.0
    adjusted_risk_max: str = "medium"
    allow_patterns: tuple = ()
    block_patterns: tuple = ()
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)


__all__ = ["PolicyOptimizationResult"]
