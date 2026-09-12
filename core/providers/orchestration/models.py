"""Orchestration models: plans, steps, results, typed artifacts.

Completed from the committed contract in tests/unit/test_orchestration.py
(X.3 — Multi-Provider Orchestration).  Pure data + behaviour, no I/O.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class ChainType(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"
    VERIFY = "verify"
    CONSENSUS = "consensus"


class ArtifactType(str, Enum):
    SOURCE_CODE = "source_code"
    TEST_SUITE = "test_suite"
    SECURITY_REPORT = "security_report"
    REVIEW_REPORT = "review_report"
    RESEARCH_REPORT = "research_report"
    DOCUMENTATION = "documentation"
    UNKNOWN = "unknown"


_ARTIFACT_ALIASES: dict[str, ArtifactType] = {
    "source_code": ArtifactType.SOURCE_CODE,
    "code": ArtifactType.SOURCE_CODE,
    "test_code": ArtifactType.TEST_SUITE,
    "test_suite": ArtifactType.TEST_SUITE,
    "tests": ArtifactType.TEST_SUITE,
    "security_report": ArtifactType.SECURITY_REPORT,
    "review_report": ArtifactType.REVIEW_REPORT,
    "review": ArtifactType.REVIEW_REPORT,
    "research_report": ArtifactType.RESEARCH_REPORT,
    "research": ArtifactType.RESEARCH_REPORT,
    "documentation": ArtifactType.DOCUMENTATION,
    "docs": ArtifactType.DOCUMENTATION,
}


def infer_artifact_type(key: str) -> ArtifactType:
    """Map an artifact key to its :class:`ArtifactType` (UNKNOWN when unclear)."""
    value = str(key or "").strip().lower()
    if value in _ARTIFACT_ALIASES:
        return _ARTIFACT_ALIASES[value]
    for artifact_type in ArtifactType:
        if artifact_type.value == value:
            return artifact_type
    return ArtifactType.UNKNOWN


def typed_artifact_from(key: str, path: str, summary: Optional[str] = None) -> "TypedArtifact":
    """Build a TypedArtifact from a raw artifact key/path pair."""
    return TypedArtifact(
        type=infer_artifact_type(key),
        path=str(path or ""),
        summary=str(summary) if summary else f"Artifact from {key}",
    )


@dataclass
class StepDependency:
    step_id: str
    required_artifact: str = ""


@dataclass
class TypedArtifact:
    type: ArtifactType = ArtifactType.UNKNOWN
    path: str = ""
    summary: str = ""

    @property
    def is_source(self) -> bool:
        return self.type == ArtifactType.SOURCE_CODE

    @property
    def is_test(self) -> bool:
        return self.type == ArtifactType.TEST_SUITE

    @property
    def is_report(self) -> bool:
        return self.type in (
            ArtifactType.SECURITY_REPORT,
            ArtifactType.REVIEW_REPORT,
            ArtifactType.RESEARCH_REPORT,
        )


@dataclass
class StepConfidence:
    confidence: float = 0.0
    quality_score: float = 0.0
    cost: float = 0.0
    risk: float = 0.0

    @property
    def is_reliable(self) -> bool:
        return self.confidence >= 0.8 and self.quality_score >= 0.5 and self.risk <= 0.3

    @property
    def summary(self) -> str:
        return (
            f"conf={self.confidence:.2f} quality={self.quality_score:.2f} "
            f"cost=${self.cost:.2f} risk={self.risk:.2f}"
        )


@dataclass
class ProviderStep:
    step_id: str
    task: dict[str, Any] = field(default_factory=dict)
    chain_type: ChainType = ChainType.SEQUENTIAL
    provider_id: str = ""
    label: str = ""
    dependencies: list[StepDependency] = field(default_factory=list)
    max_retries: int = 2
    timeout: int = 300

    def __post_init__(self) -> None:
        if not self.label:
            self.label = f"{self.chain_type.value}:{self.task.get('goal', '')}"

    def is_ready(self, completed_step_ids: set[str]) -> bool:
        return all(dep.step_id in completed_step_ids for dep in self.dependencies)


@dataclass
class StepResult:
    step_id: str
    provider_id: str
    chain_type: ChainType
    success: bool
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    artifacts: dict[str, Any] = field(default_factory=dict)
    typed_artifacts: list[TypedArtifact] = field(default_factory=list)
    confidence: StepConfidence = field(default_factory=StepConfidence)
    attempts: int = 1
    replan_of: str = ""

    @property
    def passed(self) -> bool:
        return self.success

    @property
    def failed(self) -> bool:
        return not self.success


@dataclass
class OrchestrationPlan:
    goal: str
    plan_id: str = field(default_factory=lambda: f"plan_{uuid4().hex[:12]}")
    steps: list[ProviderStep] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    def add_step(self, step: ProviderStep) -> None:
        self.steps.append(step)

    def step_ids(self) -> list[str]:
        return [step.step_id for step in self.steps]

    def get_step(self, step_id: str) -> Optional[ProviderStep]:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def provider_count(self) -> int:
        return len({step.provider_id for step in self.steps if step.provider_id})

    def summary(self) -> str:
        lines = [f"Plan {self.plan_id}: {self.goal}", f"Steps: {len(self.steps)}"]
        for step in self.steps:
            lines.append(
                f"  - {step.step_id} [{step.provider_id or 'unassigned'}] "
                f"({step.chain_type.value}) {step.label}"
            )
        return "\n".join(lines)


@dataclass
class OrchestrationResult:
    plan: OrchestrationPlan
    overall_success: bool = False
    step_results: list[StepResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration_ms(self) -> float:
        if self.end_time > self.start_time:
            return (self.end_time - self.start_time) * 1000.0
        return 0.0

    def get_step_result(self, step_id: str) -> Optional[StepResult]:
        for step_result in self.step_results:
            if step_result.step_id == step_id:
                return step_result
        return None

    def collect_outputs(self) -> dict[str, str]:
        return {r.step_id: r.output for r in self.step_results if r.success}

    def collect_artifacts(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for step_result in self.step_results:
            if step_result.success:
                merged.update(step_result.artifacts)
        return merged

    def collect_typed_artifacts(self) -> list[TypedArtifact]:
        seen: set[str] = set()
        collected: list[TypedArtifact] = []
        for step_result in self.step_results:
            for artifact in step_result.typed_artifacts:
                if artifact.path and artifact.path in seen:
                    continue
                if artifact.path:
                    seen.add(artifact.path)
                collected.append(artifact)
        return collected

    def collect_confidence(self) -> dict[str, StepConfidence]:
        return {r.step_id: r.confidence for r in self.step_results}

    @property
    def successful_steps(self) -> list[StepResult]:
        return [r for r in self.step_results if r.success]

    @property
    def failed_steps(self) -> list[StepResult]:
        return [r for r in self.step_results if not r.success]

    @property
    def avg_confidence(self) -> float:
        if not self.step_results:
            return 0.0
        return sum(r.confidence.confidence for r in self.step_results) / len(self.step_results)

    @property
    def avg_quality(self) -> float:
        if not self.step_results:
            return 0.0
        return sum(r.confidence.quality_score for r in self.step_results) / len(self.step_results)

    @property
    def total_cost(self) -> float:
        return sum(r.confidence.cost for r in self.step_results)

    @property
    def overall_risk(self) -> float:
        if not self.step_results:
            return 0.0
        return sum(r.confidence.risk for r in self.step_results) / len(self.step_results)

    def summary(self) -> str:
        status = "SUCCESS" if self.overall_success else "FAIL"
        lines = [
            f"[{status}] Plan {self.plan.plan_id}: {self.plan.goal}",
            f"Steps: {len(self.successful_steps)}/{len(self.step_results)} succeeded",
        ]
        for step_result in self.step_results:
            lines.append(
                f"  - {step_result.step_id} ({step_result.provider_id}): "
                f"{step_result.confidence.summary}"
            )
        if self.end_time > self.start_time:
            lines.append(f"Duration: {self.duration_ms:.0f}ms")
        return "\n".join(lines)
