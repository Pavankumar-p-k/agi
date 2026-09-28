"""CapabilityNegotiator — picks the best provider for a capability node.

Deterministic: identical inputs produce identical outputs (Gate 5).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from core.capability.graph import capability_graph


@dataclass
class CandidateScore:
    provider_id: str
    provider_version: str
    score: float
    confidence: float
    dimensions: dict
    calibration_adjustment: float = 0.0
    reason: str = ""


@dataclass
class NegotiationResult:
    capability_id: str
    capability_version: int
    chosen_provider_id: str
    chosen_provider_version: str
    score: float
    confidence: float
    candidates: Tuple[CandidateScore, ...] = ()
    fallback_chain: Tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "chosen_provider_id": self.chosen_provider_id,
            "chosen_provider_version": self.chosen_provider_version,
            "score": self.score,
            "confidence": self.confidence,
            "candidates": [
                {
                    "provider_id": c.provider_id,
                    "provider_version": c.provider_version,
                    "score": c.score,
                    "confidence": c.confidence,
                    "dimensions": dict(c.dimensions),
                    "calibration_adjustment": c.calibration_adjustment,
                    "reason": c.reason,
                }
                for c in self.candidates
            ],
            "fallback_chain": list(self.fallback_chain),
            "reason": self.reason,
        }


class CapabilityNegotiator:
    """Resolves a CapabilityNode to a provider via the router + registry."""

    def __init__(self, graph: Any = None, router: Any = None,
                 registry: Any = None) -> None:
        self.graph = graph
        self.router = router
        self.registry = registry

    def _score_candidates(self, capability_id: str) -> list:
        providers = []
        registered_priorities: dict = {}
        if self.registry is not None and hasattr(self.registry, "providers_for_capability"):
            providers = self.registry.providers_for_capability(capability_id)
            registered_priorities = getattr(self.registry, "_priorities", {}) or {}
        elif self.router is not None:
            chain_fn = getattr(self.router, "_select_chain", None)
            if callable(chain_fn):
                providers = chain_fn(capability_id)

        candidates: list = []
        for p in providers:
            pid = getattr(p, "provider_id", "") or type(p).__name__
            version = str(getattr(p, "version", "1.0.0"))
            # The registry's recorded priority is authoritative (instances
            # often share a class-level default).
            priority = int(registered_priorities.get(pid,
                                                     getattr(p, "priority", 50)))
            score = round(min(1.0, priority / 100.0), 3)
            candidates.append(CandidateScore(
                provider_id=pid,
                provider_version=version,
                score=score,
                confidence=score,
                dimensions={"priority": priority},
                calibration_adjustment=0.0,
                reason=f"priority={priority}",
            ))
        candidates.sort(key=lambda c: (-c.score, c.provider_id))
        return candidates

    def resolve(self, node: Any) -> NegotiationResult:
        capability_id = getattr(node, "capability_id", "") or ""
        capability_version = int(getattr(node, "version", 1) or 1)

        candidates = self._score_candidates(capability_id)
        if not candidates:
            return NegotiationResult(
                capability_id=capability_id,
                capability_version=capability_version,
                chosen_provider_id="",
                chosen_provider_version="",
                score=0.0,
                confidence=0.0,
                candidates=(),
                fallback_chain=(),
                reason="no provider offers this capability",
            )

        best = candidates[0]
        fallback = tuple(c.provider_id for c in candidates[1:])
        return NegotiationResult(
            capability_id=capability_id,
            capability_version=capability_version,
            chosen_provider_id=best.provider_id,
            chosen_provider_version=best.provider_version,
            score=best.score,
            confidence=best.confidence,
            candidates=tuple(candidates),
            fallback_chain=fallback,
            reason=f"{best.reason} (score={best.score:.2f}, "
                   f"conf={best.confidence:.2f})",
        )


# Module-level default negotiator wired to the shared capability graph.
capability_negotiator = CapabilityNegotiator(graph=capability_graph)


__all__ = ["CandidateScore", "NegotiationResult", "CapabilityNegotiator",
           "capability_negotiator"]
