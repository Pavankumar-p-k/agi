from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


class RecoveryMode(str, enum.Enum):
    """How a workflow reached its outcome.

    Values ordered from best to worst outcome path:
      FIRST_TRY            — completed without any retry or recovery
      AFTER_RETRY          — completed after at least one step-level retry
      AFTER_REPLAN         — completed after planner-level replanning
      AFTER_PROVIDER_SWAP  — completed after a provider was swapped mid-execution
      AFTER_COMPENSATION   — completed only after reverse-rolling completed steps
      AFTER_HUMAN_APPROVAL — completed after human intervention
      FAILED               — did not complete
    """

    FIRST_TRY = "FIRST_TRY"
    AFTER_RETRY = "AFTER_RETRY"
    AFTER_REPLAN = "AFTER_REPLAN"
    AFTER_PROVIDER_SWAP = "AFTER_PROVIDER_SWAP"
    AFTER_COMPENSATION = "AFTER_COMPENSATION"
    AFTER_HUMAN_APPROVAL = "AFTER_HUMAN_APPROVAL"
    FAILED = "FAILED"


@dataclass
class ProviderEntry:
    """Structured record of one provider's contribution to a workflow.

    Enables future analytics like per-provider success rates, cost
    breakdowns, and capability-level benchmarking.
    """

    provider: str = ""
    capability: str = ""
    duration_ms: float = 0.0
    success: bool = False
    retries: int = 0
    cost: float = 0.0


@dataclass(frozen=True)
class WorkflowTemplate:
    """Immutable blueprint for a workflow.

    This is the learning system's template representation, distinct from
    the planner's internal PlannerTemplate. Each version learns independently.
    """

    template_id: str
    version: int = 1
    name: str = ""
    description: str = ""
    capabilities_required: list[str] = field(default_factory=list)
    orchestration_graph: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        """Human-readable name with version, e.g. android_build@2."""
        if self.version > 1:
            return f"{self.template_id}@{self.version}"
        return self.template_id


@dataclass(frozen=True)
class WorkflowFingerprint:
    """Immutable context key for workflow calibration.

    The hash of this fingerprint is the lookup key into calibration data.
    Designed to be broader than the provider-level (language, framework, size)
    context key so workflows can be discriminated by more dimensions.
    """

    task_type: str = ""
    complexity: str = ""
    project_size: str = ""
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    artifact_types: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    context_json: str = ""

    def __hash__(self) -> int:
        return hash(self.context_key())

    def context_key(self) -> str:
        """Deterministic string key for lookup.

        Uses only the non-empty fields so partial fingerprints match
        the same way provider-level context fallback works.
        """
        parts: list[str] = []
        if self.task_type:
            parts.append(f"t:{self.task_type}")
        if self.complexity:
            parts.append(f"c:{self.complexity}")
        if self.project_size:
            parts.append(f"s:{self.project_size}")
        if self.languages:
            parts.append(f"l:{','.join(sorted(self.languages))}")
        if self.frameworks:
            parts.append(f"f:{','.join(sorted(self.frameworks))}")
        if self.capabilities:
            parts.append(f"p:{','.join(sorted(self.capabilities))}")
        if self.artifact_types:
            parts.append(f"a:{','.join(sorted(self.artifact_types))}")
        if self.requirements:
            parts.append(f"r:{','.join(sorted(self.requirements))}")
        return "|".join(parts)


@dataclass
class WorkflowInstance:
    """Record of one workflow execution for learning purposes.

    This is the learning system's view of an execution — distinct from
    the engine's mutable WorkflowInstance. It links an execution to its
    template, fingerprint, and eventual outcome.
    """

    workflow_id: str = field(default_factory=lambda: f"wf_{uuid4().hex[:12]}")
    template_id: str = ""
    template_version: int = 1
    fingerprint: WorkflowFingerprint | None = None
    status: str = "PENDING"
    started_at: float = 0.0
    completed_at: float = 0.0


@dataclass
class WorkflowOutcome:
    """Summary of a completed workflow execution.

    Produced by WorkflowExecutionRecorder after observing a full execution
    through the Activity Graph. Append-only — never updated in place.
    """

    workflow_id: str = ""
    template_id: str = ""
    template_version: int = 1
    fingerprint: WorkflowFingerprint | None = None
    success: bool = False
    duration_ms: float = 0.0
    cost: float = 0.0
    quality: float = 0.0
    recovery_mode: RecoveryMode = RecoveryMode.FIRST_TRY
    artifacts: list[str] = field(default_factory=list)
    error_categories: list[str] = field(default_factory=list)
    provider_summary: list[dict[str, Any]] = field(default_factory=list)
    activity_graph_id: str = ""

    @property
    def fingerprint_key(self) -> str:
        """Convenience accessor; returns empty string if no fingerprint."""
        if self.fingerprint is not None:
            return self.fingerprint.context_key()
        return ""


# ── Fingerprint fallback chain ──────────────────────────────────────────

_FINGERPRINT_FALLBACK_CHAIN: list[tuple[int, int, int, int]] = [
    (4, 3, 2, 1),
    (4, 3, 2, 0),
    (4, 3, 0, 0),
    (4, 0, 0, 0),
    (0, 0, 0, 0),
]
"""Fallback chain for fingerprint-based calibration lookup.

Each entry is (include_task_type, include_languages, include_frameworks,
include_project_size) where >0 = include, 0 = exclude.

Walks from most specific to least specific.
"""


def _fingerprint_fallback_key(
    task_type: str,
    languages: str = "",
    frameworks: str = "",
    project_size: str = "",
) -> str:
    """Build a partial fingerprint key at a specific granularity.

    Uses the same key format as WorkflowFingerprint.context_key() so
    partial keys can match against stored fingerprint_key values.
    """
    parts: list[str] = []
    if task_type:
        parts.append(f"t:{task_type}")
    if languages:
        # Languages stored as comma-joined sorted list
        langs = ",".join(sorted(l.strip() for l in languages.split(",") if l.strip()))
        if langs:
            parts.append(f"l:{langs}")
    if frameworks:
        fws = ",".join(sorted(f.strip() for f in frameworks.split(",") if f.strip()))
        if fws:
            parts.append(f"f:{fws}")
    if project_size:
        parts.append(f"s:{project_size}")
    return "|".join(parts)


def _parse_fingerprint_key(key: str) -> dict[str, str]:
    """Parse a fingerprint_key string into its component dimensions.

    Returns dict with keys: task_type, languages, frameworks, project_size.
    Missing fields default to empty strings.
    """
    result: dict[str, str] = {
        "task_type": "",
        "languages": "",
        "frameworks": "",
        "project_size": "",
    }
    if not key:
        return result
    for part in key.split("|"):
        part = part.strip()
        if part.startswith("t:"):
            result["task_type"] = part[2:]
        elif part.startswith("l:"):
            result["languages"] = part[2:]
        elif part.startswith("f:"):
            result["frameworks"] = part[2:]
        elif part.startswith("s:"):
            result["project_size"] = part[2:]
    return result
