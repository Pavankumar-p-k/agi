"""Opportunity Discovery (17) — Calibration (17.1) — Graph (19) — Mining (20)
   — Forecasting (21) — Bottlenecks (22) — Roadmap (23).

Answers: "What should JARVIS improve first, in what sequence?"

Phase 17:  Discovers opportunities from 4 sources.
Phase 17.1: Calibrates scores based on prediction accuracy.
Phase 19:  Builds dependency graphs, computes unlock_value.
Phase 20:  Learns dependencies from historical evidence.
Phase 21:  Forecasts future high-value opportunities using trend +
           bottleneck + unlock analysis. Moves from reactive to
           anticipatory optimization.
Phase 22:  Predicts bottlenecks — local + propagated impact.
Phase 23:  Generates multi-phase improvement roadmaps combining
           opportunity scores, dependency ordering, and bottleneck
           weights into sequenced execution plans.
"""

from core.opportunity.bottlenecks import Bottleneck, BottleneckAnalyzer, BottleneckImpact
from core.opportunity.calibration import OpportunityCalibrator
from core.opportunity.engine import OpportunityDiscoveryEngine, DEFAULT_SYSTEM_SCORES
from core.opportunity.forecasting import (
    DEFAULT_VELOCITY,
    ForecastingEngine,
    ForecastHorizon,
    ForecastResult,
    ForecastTrend,
    ForecastedOpportunity,
    HistoricalDataPoint,
)
from core.opportunity.graph import (
    DEFAULT_UNLOCK_VALUE,
    OpportunityGraph,
    OpportunityGraphBuilder,
    OpportunityGraphEdge,
    OpportunityGraphNode,
    UnlockValueScorer,
    build_default_graph,
)
from core.opportunity.mining import (
    EdgeSource,
    MinedEdge,
    PromotionRules,
    SequentialPatternMiner,
)
from core.opportunity.models import (
    Opportunity,
    OpportunitySource,
    OpportunityStatus,
)
from core.opportunity.roadmap import Roadmap, RoadmapGenerator, RoadmapItem, RoadmapPhase
from core.opportunity.store import OpportunityRecord, OpportunityStore

__all__ = [
    "Bottleneck",
    "BottleneckAnalyzer",
    "BottleneckImpact",
    "DEFAULT_SYSTEM_SCORES",
    "DEFAULT_UNLOCK_VALUE",
    "DEFAULT_VELOCITY",
    "EdgeSource",
    "ForecastHorizon",
    "ForecastResult",
    "ForecastTrend",
    "ForecastedOpportunity",
    "ForecastingEngine",
    "HistoricalDataPoint",
    "MinedEdge",
    "Opportunity",
    "OpportunityCalibrator",
    "OpportunityDiscoveryEngine",
    "OpportunityGraph",
    "OpportunityGraphBuilder",
    "OpportunityGraphEdge",
    "OpportunityGraphNode",
    "OpportunityRecord",
    "OpportunitySource",
    "OpportunityStatus",
    "OpportunityStore",
    "PromotionRules",
    "Roadmap",
    "RoadmapGenerator",
    "RoadmapItem",
    "RoadmapPhase",
    "SequentialPatternMiner",
    "UnlockValueScorer",
    "build_default_graph",
]
