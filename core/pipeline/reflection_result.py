"""ReflectionResult — output of the reflection stage."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReflectionResult:
    reflection_id: str = ""
    activity_id: str = ""
    question: str = ""
    success_rating: float = 0.0
    overall_confidence: float = 0.0
    lessons: tuple = ()
    patterns: tuple = ()
    total_facts_collected: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["ReflectionResult"]
