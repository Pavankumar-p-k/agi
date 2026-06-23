"""Phase 10 — Adaptive Behavior System.

The system never modifies source code directly. Instead, it adjusts
named "behavior knobs" — typed, ranged, auditable parameters that
existing subsystems read at runtime.

Pipeline:
  KnowledgeStore → ImprovementDetector → ProposalEngine
      → ExperimentRunner → MetricsEvaluator → SafePromotion
          → KnobStore (permanent) or Rollback
"""

from core.improvement.detector import ImprovementDetector
from core.improvement.experiment import ExperimentRunner
from core.improvement.knob_store import KnobStore
from core.improvement.models import (
    BehaviorKnob,
    Experiment,
    ExperimentResult,
    ExperimentStatus,
    ImprovementProposal,
    KnobCategory,
    KnobChange,
    KNOB_REGISTRY,
    MetricComparison,
)
from core.improvement.proposals import ProposalEngine
from core.improvement.promoter import SafePromotion

__all__ = [
    "BehaviorKnob",
    "KnobCategory",
    "KnobChange",
    "ImprovementProposal",
    "Experiment",
    "ExperimentStatus",
    "ExperimentResult",
    "MetricComparison",
    "KNOB_REGISTRY",
    "KnobStore",
    "ImprovementDetector",
    "ProposalEngine",
    "ExperimentRunner",
    "SafePromotion",
]
