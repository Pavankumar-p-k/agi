"""Opportunity Discovery (Phase 17) — Calibration (17.1) — Graph (19) — Mining (20) — Bottlenecks (22).

Answers: "What should JARVIS improve first?"

Phase 17: Discovers opportunities from 4 sources.
Phase 17.1: Calibrates scores based on prediction accuracy.
Phase 19: Builds dependency graphs, computes unlock_value.
Phase 20: Learns dependencies from historical evidence.
Phase 22: Predicts which subsystem weaknesses cause the most downstream
          damage — propagates local impact through the learned graph.

Scoring formula (7-dimensional for bottleneck analysis):

    total_constrained_value = local_impact + propagated_impact

    propagated_impact(node) = SUM over reachable nodes of:
        downstream.local_impact * edge.confidence * depth_discount^depth
"""

from core.opportunity.bottlenecks import Bottleneck, BottleneckAnalyzer, BottleneckImpact
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
    "Bottleneck",
    "BottleneckAnalyzer",
    "BottleneckImpact",
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
