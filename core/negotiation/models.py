"""Negotiation models — opinions, sessions, consensus."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AgentOpinion:
    """An opinion from a single agent on a goal."""
    agent_name: str
    position: str
    confidence: float
    reasoning: str
    evidence_sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "position": self.position,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "evidence_sources": self.evidence_sources,
            "metadata": self.metadata,
        }


@dataclass
class ConsensusResult:
    """The result of negotiation — decision, confidence, dissent."""
    decision: str
    confidence: float
    reasoning: str
    dissent: list[str] = field(default_factory=list)
    individual_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "dissent": self.dissent,
            "individual_scores": self.individual_scores,
        }
