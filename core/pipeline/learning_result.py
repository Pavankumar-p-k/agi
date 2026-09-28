"""LearningResult models — LearningRecord per intelligence replay contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LearningRecord:
    learning_id: str = ""
    activity_id: str = ""
    reflection_id: str = ""
    success_rating: float = 0.0
    confidence: float = 0.0
    contradictions: int = 0
    patterns: tuple = ()
    lessons: tuple = ()
    strategies_used: tuple = ()
    total_facts: int = 0
    sources_count: int = 0
    store_decision: str = "skip"
    metadata: dict = field(default_factory=dict)


__all__ = ["LearningRecord"]
