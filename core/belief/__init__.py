"""Belief Quality Engine (Phase 16.0–16.2).

Unified confidence computation across all knowledge systems.

The core insight: confidence should not be a single heuristic number.
It should be a product of independently measurable dimensions:

    confidence = source_quality × evidence_strength × accuracy × freshness × consensus

Components:
  - models: data models (SourceProfile, DecomposedConfidence, etc.)
  - source_tracker: source reliability tracking
  - freshness: time-based evidence decay
  - accuracy: prediction accuracy tracking
  - consensus: cross-source corroboration scoring
  - quality: QualityEngine — unified confidence computation
  - store: SQLite-backed persistence
  - integration: hooks into existing systems (KnowledgeSynthesizer,
    OutcomePredictor, PrincipleValidator, CalibrationStore)
"""

from core.belief.accuracy import AccuracyTracker
from core.belief.consensus import ConsensusScorer
from core.belief.freshness import FreshnessScorer
from core.belief.integration import BeliefIntegrator
from core.belief.models import (
    AccuracyRecord,
    BeliefCategory,
    BeliefQualityRequest,
    DecomposedConfidence,
    DomainAccuracyMetrics,
    SourceProfile,
    SourceType,
)
from core.belief.quality import QualityEngine
from core.belief.source_tracker import SourceTracker
from core.belief.store import BeliefStore

__all__ = [
    "AccuracyTracker",
    "BeliefIntegrator",
    "BeliefQualityRequest",
    "BeliefCategory",
    "ConsensusScorer",
    "DecomposedConfidence",
    "DomainAccuracyMetrics",
    "FreshnessScorer",
    "QualityEngine",
    "SourceTracker",
    "SourceProfile",
    "SourceType",
    "AccuracyRecord",
    "BeliefStore",
]
