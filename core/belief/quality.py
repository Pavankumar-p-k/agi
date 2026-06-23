"""QualityEngine — unified confidence computation across all knowledge systems.

The core formula (5-dimensional product):

    confidence = source_quality × evidence_strength × accuracy × freshness × consensus

Each dimension is independently derived and defaults to neutral when no data
is available. The consensus dimension penalizes single-source claims and
contradictory evidence while rewarding independent corroboration.

Defaults are conservative: when a dimension has no data, it defaults to 0.5
(neutral) for source-related factors, 1.0 (current) for freshness, and 1.0
(no penalty) for consensus.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.belief.consensus import ConsensusScorer
from core.belief.freshness import FreshnessScorer
from core.belief.models import (
    BeliefCategory,
    BeliefQualityRequest,
    DecomposedConfidence,
)
from core.belief.source_tracker import SourceTracker
from core.belief.accuracy import AccuracyTracker

logger = logging.getLogger(__name__)

# Evidence strength saturating constants
EVIDENCE_SATURATION = 20  # at 20 pieces of evidence, strength = 1.0
EVIDENCE_HALF_SATURATION = 5  # at 5 pieces, strength = 0.5

# When no evidence exists, minimum strength floor
MIN_EVIDENCE_STRENGTH = 0.05
# When no source data exists, default source quality
DEFAULT_SOURCE_QUALITY = 0.50
# Minimum for each dimension to prevent zeroing
MIN_DIMENSION = 0.05
MAX_DIMENSION = 1.00

# How much blend toward the existing confidence when provided
EXISTING_CONFIDENCE_BLEND = 0.15


class QualityEngine:
    """Computes decomposed confidence values by combining independent quality dimensions.

    The engine is stateless — all state lives in SourceTracker, AccuracyTracker,
    FreshnessScorer, and ConsensusScorer which are injected.
    """

    def __init__(
        self,
        source_tracker: SourceTracker | None = None,
        accuracy_tracker: AccuracyTracker | None = None,
        freshness_scorer: FreshnessScorer | None = None,
        consensus_scorer: ConsensusScorer | None = None,
    ):
        self.source_tracker = source_tracker or SourceTracker()
        self.accuracy_tracker = accuracy_tracker or AccuracyTracker()
        self.freshness_scorer = freshness_scorer or FreshnessScorer()
        self.consensus_scorer = consensus_scorer or ConsensusScorer()

    def compute(self, request: BeliefQualityRequest) -> DecomposedConfidence:
        """Compute decomposed confidence for a belief quality request.

        Each dimension is computed independently:
          1. source_quality — how reliable is the originating source
          2. evidence_strength — how much supporting evidence exists
          3. accuracy — how accurate are similar beliefs in this domain
          4. freshness — how recent is the evidence
          5. consensus — how much independent corroboration exists

        The overall confidence is the product of all five dimensions,
        blended slightly with any pre-existing confidence value.
        """
        raw_category = request.category.value if isinstance(request.category, BeliefCategory) else request.category
        try:
            category = BeliefCategory(raw_category).value
        except (ValueError, AttributeError):
            category = raw_category
        domain = request.domain or "general"

        # 1. Source quality
        source_quality = self._compute_source_quality(
            request.source_id, domain
        )

        # 2. Evidence strength
        evidence_strength = self._compute_evidence_strength(
            request.evidence_count
        )

        # 3. Accuracy
        accuracy = self._compute_accuracy(domain, category, request.source_id)

        # 4. Freshness
        freshness = self.freshness_scorer.score(
            created_at=request.created_at,
            last_validated=request.last_validated,
            category=category,
        )

        # 5. Consensus
        consensus = self.consensus_scorer.score(
            supporting_sources=request.supporting_sources,
            contradicting_sources=request.contradicting_sources,
        )

        # Product across dimensions
        raw_product = source_quality * evidence_strength * accuracy * freshness * consensus
        overall = self._clamp(raw_product)

        # Blend with existing confidence if provided
        if request.current_confidence is not None:
            overall = overall * (1.0 - EXISTING_CONFIDENCE_BLEND) + request.current_confidence * EXISTING_CONFIDENCE_BLEND
            overall = self._clamp(overall)

        return DecomposedConfidence(
            overall=overall,
            source_quality=source_quality,
            evidence_strength=evidence_strength,
            accuracy=accuracy,
            freshness=freshness,
            consensus=consensus,
            components={
                "evidence_count": float(request.evidence_count),
            },
        )

    def compute_from_scratch(
        self,
        evidence_count: int = 0,
        category: str = "heuristic",
        domain: str = "general",
        source_id: str | None = None,
        created_at: datetime | None = None,
        last_validated: datetime | None = None,
        current_confidence: float | None = None,
    ) -> DecomposedConfidence:
        """Convenience method — creates a BeliefQualityRequest and computes."""
        try:
            bc = BeliefCategory(category)
        except (ValueError, AttributeError):
            bc = BeliefCategory.HEURISTIC
        return self.compute(
            BeliefQualityRequest(
                source_id=source_id,
                evidence_count=evidence_count,
                category=bc,
                domain=domain,
                created_at=created_at,
                last_validated=last_validated,
                current_confidence=current_confidence,
            )
        )

    def recompute_many(
        self,
        requests: list[BeliefQualityRequest],
    ) -> list[DecomposedConfidence]:
        """Batch recompute confidence for multiple items."""
        return [self.compute(r) for r in requests]

    def get_dimension_summary(self, request: BeliefQualityRequest) -> dict[str, str]:
        """Explain why the confidence is what it is, in human terms."""
        dc = self.compute(request)
        return {
            "overall": f"{dc.overall:.2f}",
            "source_quality": f"{dc.source_quality:.2f} — {'reliable source' if dc.source_quality > 0.7 else 'limited source data' if dc.source_quality > 0.4 else 'unreliable source'}",
            "evidence_strength": f"{dc.evidence_strength:.2f} — {'strong evidence' if dc.evidence_strength > 0.7 else 'moderate evidence' if dc.evidence_strength > 0.4 else 'weak evidence'} ({request.evidence_count} items)",
            "accuracy": f"{dc.accuracy:.2f} — {'historically accurate' if dc.accuracy > 0.7 else 'mixed accuracy' if dc.accuracy > 0.4 else 'historically inaccurate'} in domain '{request.domain or 'general'}'",
            "freshness": f"{dc.freshness:.2f} — {'recent' if dc.freshness > 0.7 else 'aging' if dc.freshness > 0.4 else 'stale'}",
            "consensus": f"{dc.consensus:.2f} — {self.consensus_scorer.dimension_summary(dc.consensus)}",
        }

    def _compute_source_quality(
        self, source_id: str | None, domain: str
    ) -> float:
        if source_id is None:
            return DEFAULT_SOURCE_QUALITY
        return self.source_tracker.get_reliability(source_id, domain=domain)

    def _compute_evidence_strength(self, count: int) -> float:
        if count <= 0:
            return MIN_EVIDENCE_STRENGTH
        if count >= EVIDENCE_SATURATION:
            return 1.0
        # Logistic-ish curve: saturating at EVIDENCE_SATURATION
        return count / (count + EVIDENCE_HALF_SATURATION)

    def _compute_accuracy(
        self, domain: str, category: str, source_id: str | None
    ) -> float:
        # Prefer domain+category accuracy, fall back to domain-only
        acc = self.accuracy_tracker.get_accuracy(
            domain=domain, category=category
        )
        if acc > 0.0 and acc != 0.5:
            return acc

        acc = self.accuracy_tracker.get_accuracy(domain=domain)
        if acc > 0.0 and acc != 0.5:
            return acc

        return 0.5

    def _clamp(self, value: float) -> float:
        return max(MIN_DIMENSION, min(MAX_DIMENSION, value))
