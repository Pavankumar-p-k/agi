"""CodingAI — structured coding capability with explicit boundaries.

The package re-exports the real submodules: repository indexing, change
planning, architecture reasoning, safe refactoring and deterministic
verification. The specialist refuses high-risk work without approval and
reports UNKNOWN rather than faking success.
"""
from __future__ import annotations

from core.coding.architecture_map import ArchitectureMapper
from core.coding.change_planner import (
    ChangePlan, ChangePlanner, ChangeStep, ChangeType, FileChange,
)
from core.coding.change_simulation import ChangeSimulation
from core.coding.coding_agent import CodingAI
from core.coding.coding_state import (
    CodingAction,
    CodingCapabilityContract,
    CodingConstraints,
    CodingResult,
    CodingStatus,
)
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.refactor_safety import RefactorSafetyEngine
from core.coding.refactoring_engine import (
    CodePatch, RefactoringEngine, RollbackSnapshot, ValidationError,
    ValidationResult,
)
from core.coding.repository_indexer import FileEntry, RepositoryIndexer
from core.coding.tool_broker import (
    CapabilityInfo,
    CodingCapability,
    CodingToolBroker,
    ToolSelection,
)
from core.coding.verification import CodingVerifier

__all__ = [
    "ArchitectureMapper",
    "CapabilityInfo",
    "ChangePlan",
    "ChangePlanner",
    "ChangeSimulation",
    "ChangeStep",
    "ChangeType",
    "CodePatch",
    "CodingAI",
    "CodingAction",
    "CodingCapability",
    "CodingCapabilityContract",
    "CodingConstraints",
    "CodingResult",
    "CodingStatus",
    "CodingToolBroker",
    "CodingVerifier",
    "DependencyGraph",
    "FileChange",
    "FileEntry",
    "ImpactAnalyzer",
    "RefactorSafetyEngine",
    "RefactoringEngine",
    "RepositoryIndexer",
    "RollbackSnapshot",
    "ToolSelection",
    "ValidationError",
    "ValidationResult",
]
