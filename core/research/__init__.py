"""Research Memory — fact extraction, storage, retrieval, reasoning, and synthesis.

Transforms raw browser snapshots into structured, queryable facts
that agents can reason over across pages, sessions, and activities.
"""

from core.research.extractor import FactExtractor
from core.research.evidence_tracker import EvidenceTracker, ResearchCoverage
from core.research.gap_detector import GapDetector
from core.research.graph_models import (
    EDGE_CONTRADICTS,
    EDGE_DERIVED_FROM,
    EDGE_MENTIONS,
    EDGE_REFERENCES,
    EDGE_RELATED_TO,
    EDGE_SUPPORTS,
    GraphEdge,
    GraphNode,
)
from core.research.graph_store import GraphStore
from core.research.hypothesis import Hypothesis, HypothesisManager
from core.research.knowledge_graph import KnowledgeGraph
from core.research.linker import Linker
from core.research.models import Fact
from core.research.planner import ResearchPlan, ResearchPlanner, PlanStatus, GoalStatus
from core.research.reasoner import FactReasoner, FactComparison
from core.research.reasoning import Belief, BeliefState, Conclusion, CounterHypothesis, ReasoningEngine
from core.research.reflection import ResearchReflection, ReflectionResult
from core.research.retriever import FactRetriever
from core.research.storage import FactStore
from core.research.synthesizer import FactSynthesizer, ResearchReport

__all__ = [
    "Fact",
    "FactExtractor",
    "FactRetriever",
    "FactReasoner",
    "FactComparison",
    "FactStore",
    "FactSynthesizer",
    "ResearchReport",
    "KnowledgeGraph",
    "GraphNode",
    "GraphEdge",
    "GraphStore",
    "Linker",
    "EDGE_SUPPORTS",
    "EDGE_CONTRADICTS",
    "EDGE_REFERENCES",
    "EDGE_DERIVED_FROM",
    "EDGE_MENTIONS",
    "EDGE_RELATED_TO",
    "ResearchPlan",
    "ResearchPlanner",
    "PlanStatus",
    "GoalStatus",
    "Hypothesis",
    "HypothesisManager",
    "GapDetector",
    "EvidenceTracker",
    "ResearchCoverage",
    "ResearchReflection",
    "ReflectionResult",
    "Belief",
    "BeliefState",
    "Conclusion",
    "CounterHypothesis",
    "ReasoningEngine",
]
