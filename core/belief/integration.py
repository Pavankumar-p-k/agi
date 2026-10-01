"""Integration adapters tying the Belief Quality Engine to subsystems."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from core.belief.accuracy import AccuracyTracker
from core.belief.models import (
    BeliefCategory,
    BeliefQualityRequest,
    DecomposedConfidence,
    SourceType,
)
from core.belief.quality import QualityEngine
from core.belief.source_tracker import SourceTracker
from core.belief.store import BeliefStore


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class BeliefIntegrator:
    """Bridge between the belief quality engine and the wider system."""

    def __init__(self, store: Optional[BeliefStore] = None) -> None:
        self.store = store
        self.accuracy_tracker = AccuracyTracker()
        self.source_tracker = SourceTracker()
        self.quality_engine = QualityEngine(
            accuracy_tracker=self.accuracy_tracker,
            source_tracker=self.source_tracker,
        )

    # ── knowledge / prediction / evidence / principle ────────────────

    def adjust_knowledge_confidence(
        self,
        category=None,
        evidence_count: int = 0,
        domain: str = "",
        source_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        supporting_sources: Optional[List[str]] = None,
        contradicting_sources: Optional[List[str]] = None,
    ) -> DecomposedConfidence:
        return self.quality_engine.compute(
            BeliefQualityRequest(
                evidence_count=evidence_count,
                category=category,
                domain=domain,
                source_id=source_id,
                created_at=created_at,
                supporting_sources=supporting_sources,
                contradicting_sources=contradicting_sources,
            )
        )

    def adjust_prediction_confidence(
        self, domain: str = "", evidence_count: int = 0
    ) -> float:
        dc = self.quality_engine.compute(
            BeliefQualityRequest(
                evidence_count=evidence_count,
                category=BeliefCategory.PATTERN,
                domain=domain,
            )
        )
        return dc.overall

    def adjust_evidence_bundle_confidence(
        self, sample_size: int = 0, domain: str = ""
    ) -> float:
        dc = self.quality_engine.compute(
            BeliefQualityRequest(
                evidence_count=sample_size,
                category=BeliefCategory.HEURISTIC,
                domain=domain,
            )
        )
        return dc.overall

    def adjust_principle_confidence(
        self,
        discrimination: float = 0.0,
        sample_size: int = 0,
        domains: Optional[List[str]] = None,
    ) -> DecomposedConfidence:
        domains = domains or []
        domain = domains[0] if domains else ""
        dc = self.quality_engine.compute(
            BeliefQualityRequest(
                evidence_count=sample_size,
                category=BeliefCategory.PRINCIPLE,
                domain=domain,
            )
        )
        # Fold discrimination (and cross-domain breadth) into accuracy.
        sample_factor = sample_size / (sample_size + 10.0) if sample_size else 0.0
        accuracy = _clamp(
            0.5 + discrimination * sample_factor + 0.02 * len(domains)
        )
        dc.accuracy = accuracy
        dc.components["discrimination"] = discrimination
        dc.components["domain_count"] = len(domains)
        # Recompute overall so the adjusted accuracy propagates.
        dc.overall = _clamp(
            0.2 * dc.source_quality
            + 0.2 * dc.evidence_strength
            + 0.2 * dc.accuracy
            + 0.2 * dc.freshness
            + 0.2 * dc.consensus
        )
        return dc

    # ── recording ────────────────────────────────────────────────────

    def record_source_reference(
        self,
        source_id: str,
        source_type=None,
        domain: Optional[str] = None,
        was_correct: Optional[bool] = None,
    ) -> None:
        stype = source_type
        if not isinstance(stype, SourceType):
            try:
                stype = SourceType(source_type) if source_type else SourceType.TOOL
            except ValueError:
                stype = SourceType.TOOL
        self.source_tracker.record_reference(
            source_id, was_correct=was_correct, domain=domain, source_type=stype
        )

    def record_source_contradiction(
        self, source_id: str, source_type=None, domain: Optional[str] = None
    ) -> None:
        stype = source_type
        if not isinstance(stype, SourceType):
            try:
                stype = SourceType(source_type) if source_type else SourceType.TOOL
            except ValueError:
                stype = SourceType.TOOL
        profile = self.source_tracker.get_profile(source_id)
        profile.source_type = stype
        self.source_tracker.record_contradiction(source_id, domain=domain)

    def record_prediction_accuracy(
        self,
        belief_id: str,
        domain: str,
        category: str,
        predicted_value: float,
        actual_value: float,
    ) -> None:
        self.accuracy_tracker.record(
            belief_id=belief_id,
            domain=domain,
            category=category,
            predicted_value=predicted_value,
            actual_value=actual_value,
        )

    # ── persistence ──────────────────────────────────────────────────

    def persist(self) -> None:
        if self.store is None:
            return
        self.store.save_all_source_profiles(self.source_tracker.get_all_profiles())
        self.store.save_all_accuracy_records(self.accuracy_tracker.get_all_records())

    def load(self) -> None:
        if self.store is None:
            return
        self.source_tracker.set_profiles(self.store.get_all_source_profiles())
        self.accuracy_tracker.set_records(self.store.get_accuracy_records())

    def get_statistics(self) -> Dict[str, Any]:
        if self.store is not None:
            return self.store.get_statistics()
        return {
            "source_profiles": self.source_tracker.profile_count(),
            "accuracy_records": self.accuracy_tracker.record_count(),
        }
