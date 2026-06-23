"""Opportunity Discovery Engine (Phase 17) — Calibration (Phase 17.1) — Graph (Phase 19) — Mining (Phase 20).

Answers: "What should JARVIS improve first?"

Phase 17: Discovers opportunities from 4 sources (bottleneck, ceiling, experiment, principle).
Phase 17.1: Calibrates scores based on historical prediction accuracy.
Phase 19: Builds opportunity dependency graphs and computes unlock_value.
Phase 20: Learns opportunity dependencies from historical evidence via
          sequential pattern mining — transitions the graph from human-seeded
          to empirically learned.

Scoring formula (6-dimensional):

    opportunity_score = impact × headroom × success_probability
                      × confidence × calibration_accuracy × unlock_value

The 6th dimension (unlock_value) is computed from forward-reachability analysis
of the opportunity dependency graph. Edges in the graph shift from DEFAULT to
LEARNED as historical evidence accumulates.
"""

from core.opportunity.calibration import OpportunityCalibrator
from core.opportunity.engine import OpportunityDiscoveryEngine, DEFAULT_SYSTEM_SCORES
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
from core.opportunity.store import OpportunityRecord, OpportunityStore

__all__ = [
    "DEFAULT_SYSTEM_SCORES",
    "DEFAULT_UNLOCK_VALUE",
    "EdgeSource",
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
    "SequentialPatternMiner",
    "UnlockValueScorer",
    "build_default_graph",
]
