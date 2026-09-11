"""
Module: core.research.__init__
Research AI internal components and specialist interface.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from core.research.models import (
    ResearchTask,
    ResearchPlan,
    ResearchStep,
    Source,
    Evidence,
    Claim,
    Fact,
    Hypothesis,
    ResearchResult,
    ResearchReport,
    ResearchConfidence,
    ResearchError,
    Belief,
    BeliefState,
    Conclusion,
    CounterHypothesis,
)

from core.research.graph_models import (
    GraphNode,
    GraphEdge,
    EdgeType,
    KnowledgeGraph,
    KnowledgeGraphManager,
)

from core.research.extractor import Extractor

from core.research.evidence_tracker import EvidenceTracker

from core.research.linker import Linker

from core.research.planner import ResearchPlanner, ResearchPlan, ResearchStep, uuid4

from core.research.reasoner import FactReasoner, ComparisonEngine

from core.research.reasoning import (
    ReasoningEngine,
    BeliefStateTracker,
    ArgumentMapper,
)

from core.research.hypothesis import Hypothesis, HypothesisGenerator

from core.research.knowledge_graph import KnowledgeGraphManager

from core.research.graph_store import GraphStore

from core.research.synthesizer import Synthesizer, FactSynthesizer, ResearchReport

from core.research.reflection import ResearchReflection

from core.research.storage import ResearchStorage

from core.research.retriever import Retriever

from core.research._research_ai import ResearchAI

from core.research.benchmark import ResearchBenchmark

from core.research.research_benchmark import ResearchBenchmark as ResearchBench

__all__ = [
    "ResearchTask",
    "ResearchPlan",
    "ResearchStep",
    "Source",
    "Evidence",
    "Claim",
    "Fact",
    "Hypothesis",
    "ResearchResult",
    "ResearchReport",
    "ResearchConfidence",
    "ResearchError",
    "Belief",
    "BeliefState",
    "Conclusion",
    "CounterHypothesis",
    "GraphNode",
    "GraphEdge",
    "EdgeType",
    "KnowledgeGraph",
    "KnowledgeGraphManager",
    "Extractor",
    "EvidenceTracker",
    "Linker",
    "ResearchPlanner",
    "FactReasoner",
    "ComparisonEngine",
    "ReasoningEngine",
    "BeliefStateTracker",
    "ArgumentMapper",
    "Hypothesis",
    "HypothesisGenerator",
    "Synthesizer",
    "FactSynthesizer",
    "ResearchReport",
    "ResearchReflection",
    "ResearchStorage",
    "Retriever",
    "ResearchAI",
    "ResearchBenchmark",
    "ResearchBench",
]