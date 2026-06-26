from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


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
    DOCUMENTATION = "documentation"
    RESEARCH_REPORT = "research_report"
    BUILD_OUTPUT = "build_output"
    DEPLOYMENT_URL = "deployment_url"
    SCREENSHOT = "screenshot"
    TEST_RESULT = "test_result"
    FIXED_CODE = "fixed_code"
    CONFIGURATION = "configuration"
    LOG = "log"
    UNKNOWN = "unknown"


@dataclass
class StepConfidence:
    confidence: float = 0.0
    quality_score: float = 0.0
    cost: float = 0.0
    risk: float = 0.0

    @property
    def is_reliable(self) -> bool:
        return self.confidence >= 0.7 and self.risk <= 0.3

    @property
    def summary(self) -> str:
        return f"conf={self.confidence:.2f} quality={self.quality_score:.2f} cost=${self.cost:.4f} risk={self.risk:.2f}"


@dataclass
class TypedArtifact:
    type: ArtifactType
    path: str
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_source(self) -> bool:
        return self.type == ArtifactType.SOURCE_CODE

    @property
    def is_test(self) -> bool:
        return self.type == ArtifactType.TEST_SUITE

    @property
    def is_report(self) -> bool:
        return self.type in (ArtifactType.SECURITY_REPORT, ArtifactType.REVIEW_REPORT,
                             ArtifactType.RESEARCH_REPORT)


_ARTIFACT_TYPE_MAP: dict[str, ArtifactType] = {
    "source_code": ArtifactType.SOURCE_CODE,
    "test_code": ArtifactType.TEST_SUITE,
    "test_report": ArtifactType.TEST_RESULT,
    "security_report": ArtifactType.SECURITY_REPORT,
    "review_report": ArtifactType.REVIEW_REPORT,
    "documentation": ArtifactType.DOCUMENTATION,
    "fixed_code": ArtifactType.FIXED_CODE,
    "research_report": ArtifactType.RESEARCH_REPORT,
    "build_output": ArtifactType.BUILD_OUTPUT,
    "deployment_url": ArtifactType.DEPLOYMENT_URL,
    "screenshot": ArtifactType.SCREENSHOT,
    "configuration": ArtifactType.CONFIGURATION,
    "log": ArtifactType.LOG,
}


def infer_artifact_type(key: str) -> ArtifactType:
    return _ARTIFACT_TYPE_MAP.get(key, ArtifactType.UNKNOWN)


def typed_artifact_from(key: str, path: str, summary: str = "") -> TypedArtifact:
    return TypedArtifact(
        type=infer_artifact_type(key),
        path=path,
        summary=summary or f"Artifact from {key}",
    )


@dataclass
class StepDependency:
    step_id: str
    required_artifact: str = ""


@dataclass
class ProviderStep:
    step_id: str
    chain_type: ChainType = ChainType.SEQUENTIAL
    label: str = ""
    task: dict[str, Any] = field(default_factory=dict)
    provider_id: str = ""
    dependencies: list[StepDependency] = field(default_factory=list)
    expected_artifact_keys: list[str] = field(default_factory=list)
    timeout: int = 300
    retry_count: int = 0
    max_retries: int = 2

    def __post_init__(self):
        if not self.label:
            self.label = f"{self.chain_type.value}:{self.task.get('goal', self.step_id)}"

    def is_ready(self, completed: set[str]) -> bool:
        return all(d.step_id in completed for d in self.dependencies)


@dataclass
class StepResult:
    step_id: str
    provider_id: str
    chain_type: ChainType
    success: bool = False
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    artifacts: dict[str, str] = field(default_factory=dict)
    typed_artifacts: list[TypedArtifact] = field(default_factory=list)
    confidence: StepConfidence = field(default_factory=StepConfidence)
    retries: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.success

    @property
    def failed(self) -> bool:
        return not self.success


@dataclass
class OrchestrationPlan:
    plan_id: str = ""
    goal: str = ""
    steps: list[ProviderStep] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0

    def __post_init__(self):
        if not self.plan_id:
            self.plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now().timestamp()

    def add_step(self, step: ProviderStep) -> None:
        self.steps.append(step)

    def step_ids(self) -> list[str]:
        return [s.step_id for s in self.steps]

    def get_step(self, step_id: str) -> ProviderStep | None:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    def provider_count(self) -> int:
        return len({s.provider_id for s in self.steps if s.provider_id})

    def summary(self) -> str:
        lines = [f"  Plan: {self.plan_id}",
                 f"  Goal: {self.goal}",
                 f"  Steps: {self.total_steps}"]
        for s in self.steps:
            dep_str = f" → after [{', '.join(d.step_id for d in s.dependencies)}]" if s.dependencies else ""
            lines.append(f"    {s.step_id}: {s.label} [{s.chain_type.value}] via {s.provider_id or '?'}{dep_str}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "total_steps": self.total_steps,
            "provider_count": self.provider_count(),
            "created_at": self.created_at,
        }


@dataclass
class OrchestrationResult:
    plan: OrchestrationPlan
    step_results: list[StepResult] = field(default_factory=list)
    overall_success: bool = False
    start_time: float = 0.0
    end_time: float = 0.0
    error: str = ""

    def get_step_result(self, step_id: str) -> StepResult | None:
        for r in self.step_results:
            if r.step_id == step_id:
                return r
        return None

    def collect_outputs(self) -> dict[str, str]:
        return {r.step_id: r.output for r in self.step_results if r.success}

    def collect_artifacts(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for r in self.step_results:
            merged.update(r.artifacts)
        return merged

    def collect_typed_artifacts(self) -> list[TypedArtifact]:
        merged: list[TypedArtifact] = []
        seen: set[str] = set()
        for r in self.step_results:
            for ta in r.typed_artifacts:
                if ta.path not in seen:
                    merged.append(ta)
                    seen.add(ta.path)
        return merged

    def collect_confidence(self) -> dict[str, StepConfidence]:
        return {r.step_id: r.confidence for r in self.step_results}

    @property
    def avg_confidence(self) -> float:
        confs = [r.confidence.confidence for r in self.step_results if r.success]
        return sum(confs) / len(confs) if confs else 0.0

    @property
    def avg_quality(self) -> float:
        quals = [r.confidence.quality_score for r in self.step_results if r.success]
        return sum(quals) / len(quals) if quals else 0.0

    @property
    def total_cost(self) -> float:
        return sum(r.confidence.cost for r in self.step_results)

    @property
    def overall_risk(self) -> float:
        risks = [r.confidence.risk for r in self.step_results]
        return max(risks) if risks else 0.0

    @property
    def duration_ms(self) -> float:
        return self.end_time - self.start_time if self.end_time > self.start_time else 0.0

    @property
    def successful_steps(self) -> list[StepResult]:
        return [r for r in self.step_results if r.success]

    @property
    def failed_steps(self) -> list[StepResult]:
        return [r for r in self.step_results if not r.success]

    def summary(self) -> str:
        total = len(self.step_results)
        passed = len(self.successful_steps)
        lines = [
            f"  Plan: {self.plan.plan_id}",
            f"  Overall: {'PASS' if self.overall_success else 'FAIL'}",
            f"  Steps: {passed}/{total} passed",
            f"  Duration: {self.duration_ms:.0f}ms",
        ]
        if self.step_results:
            lines.append(f"  Avg confidence: {self.avg_confidence:.2f}")
            lines.append(f"  Avg quality: {self.avg_quality:.2f}")
            lines.append(f"  Total cost: ${self.total_cost:.4f}")
            lines.append(f"  Risk level: {self.overall_risk:.2f}")
        for r in self.step_results:
            status = "✓" if r.success else "✗"
            c = r.confidence
            lines.append(
                f"    {status} {r.step_id} ({r.provider_id}, {r.chain_type.value}) "
                f"— {r.duration_ms:.0f}ms  "
                f"[conf={c.confidence:.2f} qual={c.quality_score:.2f} cost=${c.cost:.4f}]"
            )
        return "\n".join(lines)
