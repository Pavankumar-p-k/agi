"""Unified confidence computation for the Belief Quality Engine."""
from __future__ import annotations

import math
from typing import List

from core.belief.accuracy import AccuracyTracker
from core.belief.consensus import ConsensusScorer
from core.belief.freshness import FreshnessScorer
from core.belief.models import (
    BeliefCategory,
    BeliefQualityRequest,
    DecomposedConfidence,
)
from core.belief.source_tracker import SourceTracker

_MIN_EVIDENCE_STRENGTH = 0.05
_EVIDENCE_SATURATION = 20.0
_BLEND_WEIGHT = 0.3

_WEIGHTS = {
    "source_quality": 0.2,
    "evidence_strength": 0.2,
    "accuracy": 0.2,
    "freshness": 0.2,
    "consensus": 0.2,
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class QualityEngine:
    """Compute decomposed, explainable belief confidence."""

    def __init__(
        self,
        accuracy_tracker: AccuracyTracker | None = None,
        source_tracker: SourceTracker | None = None,
    ) -> None:
        self.accuracy_tracker = accuracy_tracker or AccuracyTracker()
        self.source_tracker = source_tracker or SourceTracker()
        self.freshness_scorer = FreshnessScorer()
        self.consensus_scorer = ConsensusScorer()

    # ── dimensions ───────────────────────────────────────────────────

    def _compute_evidence_strength(self, count: int) -> float:
        if count <= 0:
            return _MIN_EVIDENCE_STRENGTH
        value = math.sqrt(count / _EVIDENCE_SATURATION)
        return _clamp(value, _MIN_EVIDENCE_STRENGTH, 1.0)

    def _compute_source_quality(self, request: BeliefQualityRequest) -> float:
        if request.source_id:
            return self.source_tracker.get_reliability(request.source_id)
        return 0.5

    def _compute_accuracy(self, request: BeliefQualityRequest) -> float:
        category = getattr(request.category, "value", request.category)
        return self.accuracy_tracker.get_accuracy(
            domain=request.domain or None, category=category
        )

    def _compute_freshness(self, request: BeliefQualityRequest) -> float:
        return self.freshness_scorer.score(
            created_at=request.created_at,
            last_validated=request.last_validated,
            category=request.category,
        )

    def _compute_consensus(self, request: BeliefQualityRequest) -> float:
        return self.consensus_scorer.score(
            supporting_sources=request.supporting_sources,
            contradicting_sources=request.contradicting_sources,
        )

    # ── public API ───────────────────────────────────────────────────

    def compute(self, request: BeliefQualityRequest) -> DecomposedConfidence:
        source_quality = self._compute_source_quality(request)
        evidence_strength = self._compute_evidence_strength(request.evidence_count)
        accuracy = self._compute_accuracy(request)
        freshness = self._compute_freshness(request)
        consensus = self._compute_consensus(request)

        overall = (
            _WEIGHTS["source_quality"] * source_quality
            + _WEIGHTS["evidence_strength"] * evidence_strength
            + _WEIGHTS["accuracy"] * accuracy
            + _WEIGHTS["freshness"] * freshness
            + _WEIGHTS["consensus"] * consensus
        )

        if request.current_confidence is not None:
            current = _clamp(float(request.current_confidence))
            overall = (1.0 - _BLEND_WEIGHT) * overall + _BLEND_WEIGHT * current

        components = {
            "evidence_count": float(request.evidence_count),
            "domain": request.domain,
            "category": getattr(request.category, "value", request.category),
            "source_id": request.source_id,
        }

        return DecomposedConfidence(
            overall=_clamp(overall),
            source_quality=_clamp(source_quality),
            evidence_strength=_clamp(evidence_strength),
            accuracy=_clamp(accuracy),
            freshness=_clamp(freshness),
            consensus=_clamp(consensus),
            components=components,
        )

    def compute_from_scratch(
        self,
        evidence_count: int = 0,
        category=None,
        domain: str = "",
        source_id: str | None = None,
        created_at=None,
        current_confidence: float | None = None,
    ) -> DecomposedConfidence:
        return self.compute(
            BeliefQualityRequest(
                evidence_count=evidence_count,
                category=category,
                domain=domain,
                source_id=source_id,
                created_at=created_at,
                current_confidence=current_confidence,
            )
        )

    def recompute_many(
        self, requests: List[BeliefQualityRequest]
    ) -> List[DecomposedConfidence]:
        return [self.compute(request) for request in requests]

    def get_dimension_summary(self, request: BeliefQualityRequest) -> dict:
        dc = self.compute(request)
        consensus_note = self.consensus_scorer.dimension_summary(dc.consensus)
        return {
            "overall": f"{dc.overall:.2f} — combined confidence",
            "source_quality": f"{dc.source_quality:.2f} — source reliability",
            "evidence_strength": f"{dc.evidence_strength:.2f} — evidence volume",
            "accuracy": f"{dc.accuracy:.2f} — historical prediction accuracy",
            "freshness": f"{dc.freshness:.2f} — evidence recency",
            "consensus": f"{dc.consensus:.2f} — {consensus_note}",
        }


# Backwards-compatible alias — some callers import this name.
BeliefCategory = BeliefCategory
