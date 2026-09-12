"""Capability negotiation: capability node → best live provider.

Completed from the committed contract in tests/architecture/test_capability_gates.py
(Gates 3, 5, 8).  The negotiator asks the router for ranked candidates for the
node's capability and returns a deterministic, serializable result.  When no
provider offers the capability the result stays honest: empty chosen id,
empty (not fabricated) fallback chain.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

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


def _candidate_version(provider: Any) -> str:
    return str(getattr(provider, "version", "1.0") or "1.0")


class CapabilityNegotiator:
    """Resolves a CapabilityNode to a concrete provider via the router."""

    def __init__(
        self,
        graph: Any = None,
        router: Any = None,
        registry: Any = None,
    ) -> None:
        self.graph = graph
        self.router = router
        self.registry = registry

    def _get_router(self) -> Any:
        if self.router is not None:
            return self.router
        from core.providers.router import provider_router
        return provider_router

    def _candidate_providers(self, capability_id: str) -> list[Any]:
        router = self._get_router()
        try:
            task = {"capability": capability_id}
            ranked: list[Any] = []
            seen: set[str] = set()
            for provider in router.select_with_fallback(capability_id, task, limit=5):
                if provider.provider_id in seen:
                    continue
                seen.add(provider.provider_id)
                ranked.append(provider)
            return ranked
        except Exception:
            # Router unavailable — fall back to registry ordering (Gate 3).
            if self.registry is not None:
                try:
                    return list(self.registry.get_providers_for_capability(capability_id))
                except Exception:
                    return []
            return []

    def resolve(self, node: Any) -> NegotiationResult:
        capability_id = ""
        if hasattr(node, "capability_id"):
            capability_id = getattr(node, "capability_id") or ""
        elif hasattr(node, "id"):
            capability_id = getattr(node, "id") or ""
        version = int(getattr(node, "version", 1) or 1)

        candidates = self._candidate_providers(capability_id)
        if not candidates:
            return NegotiationResult(
                capability_id=capability_id,
                capability_version=version,
                chosen_provider_id="",
                candidates=(),
                fallback_chain=(),
                reason="no provider offers this capability",
            )

        scores: list[CandidateScore] = []
        for provider in candidates:
            score = 0.0
            confidence = 0.0
            try:
                router = self._get_router()
                score = router._score(provider, {"capability": capability_id})
                confidence = router._confidence(provider)
            except Exception:
                pass
            scores.append(CandidateScore(
                provider_id=provider.provider_id,
                provider_version=_candidate_version(provider),
                score=round(score, 4),
                confidence=round(confidence, 4),
                dimensions={"priority_weight": round(score, 4)},
                calibration_adjustment=0.0,
                reason="router score",
            ))

        chosen = candidates[0]
        fallback = tuple(c.provider_id for c in candidates[1:])
        return NegotiationResult(
            capability_id=capability_id,
            provider_id=chosen.provider_id,
            score=scores[0].score,
            capability_version=version,
            chosen_provider_id=chosen.provider_id,
            chosen_provider_version=scores[0].provider_version,
            confidence=scores[0].confidence,
            candidates=tuple(scores),
            fallback_chain=fallback,
            reason=f"highest router score ({scores[0].score:.2f})",
        )


capability_negotiator = CapabilityNegotiator()
