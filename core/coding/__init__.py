"""Coding Intelligence — repository understanding, change planning, refactor safety, architecture reasoning.

Phase 8.1 — Repository Understanding:
  - RepositoryIndexer: persistent source file index with import/export extraction
  - DependencyGraph: transitive deps, reverse deps, circular detection, centrality
  - ArchitectureMapper: layer detection, pattern recognition, cross-layer edges
  - ImpactAnalyzer: what-breaks-on-change analysis, risk scoring, test selection

Phase 8.2 — Change Planning:
  - ChangePlanner: structured change plans with risk assessment and execution ordering
  - RefactorSafetyEngine: pre-edit safety checks and architecture violation detection
  - ChangeSimulation: predict breakages, detect conflicts, select tests before editing

Phase 8.3 — Safe Refactoring:
  - RefactoringEngine: patch generation, import fixing, snapshot/rollback, refactoring recipes

Phase 8.4 — Architecture Reasoning:
  - ArchitectureScorer: quantify coupling, cohesion, maintainability
  - DesignAnalyzer: detect weaknesses (god files, hub modules, circular deps)
  - TradeoffEngine: compare architectural alternatives
  - MigrationPlanner: multi-step migration between patterns
"""

from core.coding.architecture_map import (
    ArchitectureMap,
    ArchitectureMapper,
    CrossLayerEdge,
    LayerInfo,
)
from core.coding.architecture_reasoning import (
    ArchitectureScore,
    ArchitectureScorer,
    DesignAnalyzer,
    DesignReport,
    DesignWeakness,
    MigrationPlanner,
    TradeoffComparison,
    TradeoffEngine,
)
from core.coding.change_planner import ChangePlan, ChangePlanner, ChangeStep, ChangeType, FileChange
from core.coding.change_simulation import ChangeConflict, ChangeSimulation, PredictedBreakage, SimulationResult
from core.coding.dependency_graph import DependencyGraph, DependencyNode
from core.coding.impact_analyzer import ImpactAnalyzer, ImpactResult
from core.coding.refactor_safety import RefactorSafetyEngine, SafetyAssessment, SafetyWarning
from core.coding.refactoring_engine import (
    CodePatch,
    RefactoringEngine,
    RefactoringRecipe,
    RollbackSnapshot,
    ValidationResult,
)
from core.coding.repository_indexer import FileEntry, RepositoryIndexer

__all__ = [
    "FileEntry",
    "RepositoryIndexer",
    "DependencyGraph",
    "DependencyNode",
    "ArchitectureMap",
    "ArchitectureMapper",
    "CrossLayerEdge",
    "LayerInfo",
    "ImpactAnalyzer",
    "ImpactResult",
    "ChangePlan",
    "ChangePlanner",
    "ChangeStep",
    "ChangeType",
    "FileChange",
    "RefactorSafetyEngine",
    "SafetyAssessment",
    "SafetyWarning",
    "ChangeSimulation",
    "SimulationResult",
    "PredictedBreakage",
    "ChangeConflict",
    "CodePatch",
    "RefactoringEngine",
    "RefactoringRecipe",
    "RollbackSnapshot",
    "ValidationResult",
    "ArchitectureScore",
    "ArchitectureScorer",
    "DesignAnalyzer",
    "DesignReport",
    "DesignWeakness",
    "TradeoffEngine",
    "TradeoffComparison",
    "MigrationPlanner",
]

