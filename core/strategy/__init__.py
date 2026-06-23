"""Phase 12 — Strategic Reasoning Layer.

Pipeline:
  Goal → StrategyGenerator → OutcomePredictor → StrategyEvaluator → StrategySelector → Chosen Strategy

Interfaces:
  - Input: goal string (from user or planner)
  - Output: chosen Strategy + StrategyDecision (to planner + activity graph)
  - Memory: MemoryAdapter queries ActivityGraph, KnowledgeStore, ResearchMemory, ExperimentResults
  - Calibration: PredictionCalibrator closes the error loop (Phase 12.4)
"""

from core.strategy.calibration import (
    CalibrationMetrics,
    CalibrationRecord,
    CalibrationStore,
    PredictionCalibrator,
)
from core.strategy.evaluator import StrategyEvaluator
from core.strategy.generator import StrategyGenerator
from core.strategy.memory_adapter import MemoryAdapter
from core.strategy.models import (
    EvidenceBundle,
    Prediction,
    Strategy,
    StrategyDecision,
    StrategyTag,
)
from core.strategy.predictor import OutcomePredictor
from core.strategy.selector import StrategySelector
from core.strategy.similarity import SimilarityScorer

__all__ = [
    "StrategyGenerator",
    "OutcomePredictor",
    "StrategyEvaluator",
    "StrategySelector",
    "SimilarityScorer",
    "Strategy",
    "StrategyDecision",
    "Prediction",
    "StrategyTag",
    "EvidenceBundle",
    "MemoryAdapter",
    "PredictionCalibrator",
    "CalibrationStore",
    "CalibrationRecord",
    "CalibrationMetrics",
]
