"""Coding AI specialist package."""
from __future__ import annotations

from core.coding.architecture_map import ArchitectureMap, ArchitectureMapper, CrossLayerEdge, LayerInfo
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
from core.coding.coding_agent import CodingAI
from core.coding.coding_state import CodingCapabilityContract, CodingConstraints, CodingResult, CodingStatus, RiskLevel
from core.coding.dependency_graph import DependencyGraph, DependencyNode
from core.coding.impact_analyzer import ImpactAnalyzer, ImpactResult
from core.coding.refactor_safety import RefactorSafetyEngine, SafetyAssessment, SafetyWarning
from core.coding.refactoring_engine import (
    CodePatch,
    RefactoringEngine,
    RefactoringRecipe,
    RollbackSnapshot,
    ValidationError,
    ValidationResult,
)
from core.coding.repository_indexer import FileEntry, RepositoryIndexer
from core.coding.verification import CheckResult, CodingVerifier, VerificationResult

__all__ = [
    "ArchitectureMap",
    "ArchitectureMapper",
    "CrossLayerEdge",
    "LayerInfo",
    "ArchitectureScore",
    "ArchitectureScorer",
    "DesignAnalyzer",
    "DesignReport",
    "DesignWeakness",
    "MigrationPlanner",
    "TradeoffComparison",
    "TradeoffEngine",
    "ChangePlan",
    "ChangePlanner",
    "ChangeStep",
    "ChangeType",
    "FileChange",
    "ChangeConflict",
    "ChangeSimulation",
    "PredictedBreakage",
    "SimulationResult",
    "CodingAI",
    "CodingCapabilityContract",
    "CodingConstraints",
    "CodingResult",
    "CodingStatus",
    "RiskLevel",
    "DependencyGraph",
    "DependencyNode",
    "ImpactAnalyzer",
    "ImpactResult",
    "RefactorSafetyEngine",
    "SafetyAssessment",
    "SafetyWarning",
    "CodePatch",
    "RefactoringEngine",
    "RefactoringRecipe",
    "RollbackSnapshot",
    "ValidationError",
    "ValidationResult",
    "FileEntry",
    "RepositoryIndexer",
    "CheckResult",
    "CodingVerifier",
    "VerificationResult",
]
