"""
Module: core.capability.negotiation
Capability negotiation and provider selection.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class CandidateScore:
    provider_id: str = ""
    provider_version: str = ""
    score: float = 0.0
    confidence: float = 0.0
    dimensions: dict[str, float] = field(default_factory=dict)
    calibration_adjustment: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "score": self.score,
            "confidence": self.confidence,
            "dimensions": dict(self.dimensions),
            "calibration_adjustment": self.calibration_adjustment,
            "reason": self.reason,
        }


@dataclass
class NegotiationResult:
    capability_id: str = ""
    provider_id: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    capability_version: int = 1
    chosen_provider_id: str = ""
    chosen_provider_version: str = ""
    confidence: float = 0.0
    candidates: tuple[CandidateScore, ...] = ()
    fallback_chain: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "provider_id": self.provider_id,
            "score": self.score,
            "metadata": self.metadata,
            "capability_version": self.capability_version,
            "chosen_provider_id": self.chosen_provider_id or self.provider_id,
            "chosen_provider_version": self.chosen_provider_version,
            "confidence": self.confidence,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "fallback_chain": list(self.fallback_chain),
            "reason": self.reason,
        }


class CapabilityNegotiator:
    def resolve(self, node: Any) -> NegotiationResult:
        capability_id = ""
        if hasattr(node, "capability_id"):
            capability_id = node.capability_id
        elif hasattr(node, "id"):
            capability_id = node.id
        return NegotiationResult(
            capability_id=capability_id,
            provider_id=capability_id,
            score=1.0,
        )


capability_negotiator = CapabilityNegotiator()
