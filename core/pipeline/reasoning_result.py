"""ReasoningResult — output of the reasoning stage."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Belief:
    belief_id: str = ""
    claim: str = ""
    confidence: float = 0.0
    status: str = "accepted"


@dataclass
class Evidence:
    direction: str = "supports"
    weight: float = 0.0
    source: str = ""


@dataclass
class Contradiction:
    entity: str = ""
    facts: tuple = ()


@dataclass
class CounterHypothesis:
    counter_claim: str = ""
    confidence: float = 0.0


@dataclass
class ReasoningResult:
    reasoning_id: str = ""
    activity_id: str = ""
    complexity: str = "simple"
    beliefs: tuple = ()
    evidence: tuple = ()
    contradictions: tuple = ()
    counter_hypotheses: tuple = ()
    confidence: float = 0.0
    reasoning_trace: tuple = ()
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["Belief", "Evidence", "Contradiction", "CounterHypothesis",
           "ReasoningResult"]
