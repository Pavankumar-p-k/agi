"""Integrator — hooks the Belief Quality Engine into existing knowledge systems.

Provides adapter functions that plug into:
  1. KnowledgeSynthesizer — replaces simple proportion-based confidence with
     decomposed confidence from the QualityEngine.
  2. Strategy OutcomePredictor — adjusts prediction confidence using
     domain accuracy and freshness.
  3. PrincipleValidator — adjusts principle confidence using source
     quality and domain accuracy.
  4. CalibrationStore — feeds prediction accuracy data into AccuracyTracker.
  5. KnowledgeStore — records source references when knowledge is created.

All integration is optional — each function works standalone and can be
wired independently.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.belief.accuracy import AccuracyTracker, CORRECT_THRESHOLD
from core.belief.freshness import FreshnessScorer
from core.belief.models import (
    BeliefCategory,
    BeliefQualityRequest,
    DecomposedConfidence,
    SourceType,
)
from core.belief.quality import QualityEngine
from core.belief.source_tracker import SourceTracker
from core.belief.store import BeliefStore

logger = logging.getLogger(__name__)


class BeliefIntegrator:
    """Integrates the Belief Quality Engine with the rest of JARVIS.

    Wraps individual sub-engines and provides convenience methods
    that match the calling conventions of existing systems.

    Usage:
        integrator = BeliefIntegrator()
        # Hook into KnowledgeSynthesizer
        new_confidence = integrator.adjust_knowledge_confidence(
            category="pattern",
            evidence_count=5,
            domain="android",
            created_at=some_datetime,
            current_confidence=0.7,
        )
    """

    def __init__(
        self,
        store: BeliefStore | None = None,
        quality_engine: QualityEngine | None = None,
        source_tracker: SourceTracker | None = None,
        accuracy_tracker: AccuracyTracker | None = None,
        freshness_scorer: FreshnessScorer | None = None,
    ):
        self.store = store or BeliefStore()
        self.source_tracker = source_tracker or SourceTracker()
        self.accuracy_tracker = accuracy_tracker or AccuracyTracker()
        self.freshness_scorer = freshness_scorer or FreshnessScorer()
        self.quality_engine = quality_engine or QualityEngine(
            source_tracker=self.source_tracker,
            accuracy_tracker=self.accuracy_tracker,
            freshness_scorer=self.freshness_scorer,
        )

    # ── Integration with KnowledgeSynthesizer ─────────────────────────

    def adjust_knowledge_confidence(
        self,
        category: str,
        evidence_count: int,
        domain: str = "general",
        source_id: str | None = None,
        created_at: datetime | None = None,
        last_validated: datetime | None = None,
        current_confidence: float | None = None,
        supporting_sources: list[str] | None = None,
        contradicting_sources: list[str] | None = None,
    ) -> DecomposedConfidence:
        """Replace the synthesizer's simple proportion confidence.

        Called when the KnowledgeSynthesizer creates a new KnowledgeItem.
        The returned DecomposedConfidence.overall replaces the heuristic
        confidence value.

        Args:
            category: pattern|principle|heuristic|factoid|warning
            evidence_count: how many experiences support this
            domain: e.g. "android", "web", "research"
            source_id: optional source identifier
            created_at: when the knowledge was first created
            last_validated: when last confirmed
            current_confidence: the existing heuristic confidence for blending
            supporting_sources: source IDs supporting this claim
            contradicting_sources: source IDs contradicting this claim
        """
        try:
            bc = BeliefCategory(category)
        except (ValueError, AttributeError):
            bc = BeliefCategory.HEURISTIC
        request = BeliefQualityRequest(
            source_id=source_id,
            evidence_count=evidence_count,
            category=bc,
            domain=domain,
            created_at=created_at,
            last_validated=last_validated,
            current_confidence=current_confidence,
            supporting_sources=supporting_sources,
            contradicting_sources=contradicting_sources,
        )
        return self.quality_engine.compute(request)

    # ── Integration with Strategy Pipeline ────────────────────────────

    def adjust_prediction_confidence(
        self,
        domain: str,
        evidence_count: int,
        category: str = "heuristic",
        current_confidence: float | None = None,
        supporting_sources: list[str] | None = None,
        contradicting_sources: list[str] | None = None,
    ) -> float:
        """Adjust strategy prediction confidence using domain accuracy.

        Called by OutcomePredictor._blend to replace the linear
        min(0.3 + evidence_count * 0.05, 0.95) formula.
        """
        request = BeliefQualityRequest(
            evidence_count=evidence_count,
            category=BeliefCategory.HEURISTIC,
            domain=domain,
            current_confidence=current_confidence,
            supporting_sources=supporting_sources,
            contradicting_sources=contradicting_sources,
        )
        return self.quality_engine.compute(request).overall

    def adjust_evidence_bundle_confidence(
        self,
        sample_size: int,
        domain: str = "general",
    ) -> float:
        """Adjust EvidenceBundle confidence using domain accuracy.

        Called by MemoryAdapter to replace the linear
        min(sample_size / 20.0, 1.0) * 0.85 + 0.05 formula.
        """
        request = BeliefQualityRequest(
            evidence_count=sample_size,
            category=BeliefCategory.HEURISTIC,
            domain=domain,
        )
        return self.quality_engine.compute(request).overall

    # ── Integration with PrincipleValidator ──────────────────────────

    def adjust_principle_confidence(
        self,
        discrimination: float,
        sample_size: int,
        domains: list[str],
        current_confidence: float | None = None,
        supporting_sources: list[str] | None = None,
        contradicting_sources: list[str] | None = None,
    ) -> DecomposedConfidence:
        """Adjust principle confidence using belief quality.

        The PrincipleValidator currently uses a weighted formula:
            confidence = 0.45 * n_factor + 0.35 * d_factor + 0.20 * domain_factor

        This replaces that with the decomposed product approach,
        but preserves the discrimination signal via the accuracy dimension.

        Called by PrincipleValidator to produce the final confidence.
        """
        domain = domains[0] if domains else "general"
        # Discrimination signals how well this property separates success/failure
        # We map it to the accuracy dimension: strong discrimination = high accuracy
        mapped_accuracy = min(1.0, abs(discrimination) * 2.0 + 0.3)

        # Principles emerge from aggregated experiences, not a single source.
        # Source quality is neutral (1.0) when no specific source is given.
        request = BeliefQualityRequest(
            source_id="__aggregated__",
            evidence_count=sample_size,
            category=BeliefCategory.PRINCIPLE,
            domain=domain,
            current_confidence=current_confidence,
            supporting_sources=supporting_sources,
            contradicting_sources=contradicting_sources,
        )
        result = self.quality_engine.compute(request)
        # Override source_quality to 1.0 for aggregated evidence (principles
        # derive from multiple experiences, not a single source)
        result.source_quality = 1.0
        # Override the accuracy dimension with discrimination-mapped value
        result.accuracy = self._clamp(mapped_accuracy)
        # Recompute overall with all 5 dimensions (including consensus)
        result.overall = self._clamp(
            result.source_quality * result.evidence_strength * result.accuracy * result.freshness * result.consensus
        )
        return result

    # ── Source tracking hooks ─────────────────────────────────────────

    def record_source_reference(
        self,
        source_id: str,
        source_type: str = "research_url",
        domain: str = "general",
        was_correct: bool | None = None,
    ) -> None:
        """Record that a source was referenced.

        Called when a fact is extracted from a URL, or an activity completes.
        """
        try:
            st = SourceType(source_type)
        except (ValueError, AttributeError):
            st = SourceType.RESEARCH_URL
        self.source_tracker.record_reference(
            source_id=source_id,
            source_type=st,
            domain=domain,
            was_correct=was_correct,
        )

    def record_source_contradiction(
        self,
        source_id: str,
        source_type: str = "research_url",
        domain: str = "general",
    ) -> None:
        """Record that a source produced a contradictory claim."""
        try:
            st = SourceType(source_type)
        except (ValueError, AttributeError):
            st = SourceType.RESEARCH_URL
        self.source_tracker.record_contradiction(
            source_id=source_id,
            source_type=st,
            domain=domain,
        )

    # ── Accuracy tracking hooks ───────────────────────────────────────

    def record_prediction_accuracy(
        self,
        belief_id: str,
        domain: str,
        category: str,
        predicted_value: float,
        actual_value: float,
        source_id: str | None = None,
    ) -> None:
        """Record whether a prediction was accurate.

        Called by CalibrationStore when strategy outcomes are recorded.
        """
        self.accuracy_tracker.record(
            belief_id=belief_id,
            domain=domain,
            category=category,
            predicted_value=predicted_value,
            actual_value=actual_value,
            source_id=source_id,
        )

    # ── Persistence ───────────────────────────────────────────────────

    def persist(self) -> None:
        """Save all in-memory state to SQLite."""
        if not self.store:
            return
        self.store.save_all_source_profiles(self.source_tracker.get_all_profiles())
        self.store.save_all_accuracy_records(self.accuracy_tracker.get_all_records())

    def load(self) -> None:
        """Load all state from SQLite into memory."""
        if not self.store:
            return
        self.source_tracker.set_profiles(self.store.get_all_source_profiles())
        self.accuracy_tracker.set_records(self.store.get_all_accuracy_records())

    def get_statistics(self) -> dict[str, Any]:
        return {
            "source_profiles": self.source_tracker.profile_count(),
            "accuracy_records": self.accuracy_tracker.record_count(),
            "store": self.store.get_statistics() if self.store else {},
        }

    def _clamp(self, value: float) -> float:
        return max(0.1, min(1.0, value))
