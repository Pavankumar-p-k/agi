"""Multi-provider orchestration: plans, executes, verifies, and records.

Real modules — no DynamicStub machinery.  Re-exports the public surface.
"""
from __future__ import annotations

from core.providers.orchestration.models import (
    ArtifactType,
    ChainType,
    OrchestrationPlan,
    OrchestrationResult,
    ProviderStep,
    StepConfidence,
    StepDependency,
    StepResult,
    TypedArtifact,
    infer_artifact_type,
    typed_artifact_from,
)
from core.providers.orchestration.planner import (
    _SUB_TASK_PATTERNS,
    OrchestrationPlanner,
    _detect_pattern,
)
from core.providers.orchestration.orchestrator import Orchestrator
from core.providers.orchestration.adapt import AdaptEngine, ReplanLevel
from core.providers.orchestration.store import (
    OrchestrationStore,
    get_orchestration_store,
    orchestration_store,
)

__all__ = [
    "ArtifactType",
    "ChainType",
    "OrchestrationPlan",
    "OrchestrationResult",
    "ProviderStep",
    "StepConfidence",
    "StepDependency",
    "StepResult",
    "TypedArtifact",
    "infer_artifact_type",
    "typed_artifact_from",
    "OrchestrationPlanner",
    "_SUB_TASK_PATTERNS",
    "_detect_pattern",
    "Orchestrator",
    "AdaptEngine",
    "ReplanLevel",
    "OrchestrationStore",
    "orchestration_store",
    "get_orchestration_store",
]
