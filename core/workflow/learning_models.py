"""Phase 1 X.9 learning models.

Data models for workflow outcome tracking, fingerprinting, and recovery-mode
classification used by the learning store, calibration engine, and recorder.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class RecoveryMode(str, Enum):
    """How a workflow run reached its terminal state."""

    FIRST_TRY = "FIRST_TRY"
    AFTER_RETRY = "AFTER_RETRY"
    AFTER_REPLAN = "AFTER_REPLAN"
    AFTER_PROVIDER_SWAP = "AFTER_PROVIDER_SWAP"
    AFTER_COMPENSATION = "AFTER_COMPENSATION"
    AFTER_HUMAN_APPROVAL = "AFTER_HUMAN_APPROVAL"
    FAILED = "FAILED"


@dataclass
class ProviderEntry:
    """One provider's participation in a workflow run."""

    provider: str = ""
    capability: str = ""
    duration_ms: float = 0.0
    success: bool = False
    retries: int = 0
    cost: float = 0.0


@dataclass(frozen=True)
class WorkflowTemplate:
    """A reusable workflow template with a version identifier."""

    template_id: str
    version: int = 1
    name: str | None = None
    description: str | None = None
    capabilities_required: list[str] = field(default_factory=list)
    orchestration_graph: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        if self.version > 1:
            return f"{self.template_id}@{self.version}"
        return self.template_id


@dataclass
class WorkflowFingerprint:
    """Dimension set identifying a class of workflow executions."""

    task_type: str = ""
    complexity: str = ""
    project_size: str = ""
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    artifact_types: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    context_json: str = ""

    def context_key(self) -> str:
        parts: list[str] = []
        if self.task_type:
            parts.append(f"t:{self.task_type}")
        if self.complexity:
            parts.append(f"c:{self.complexity}")
        if self.project_size:
            parts.append(f"s:{self.project_size}")
        if self.languages:
            parts.append("l:" + ",".join(sorted(self.languages)))
        if self.frameworks:
            parts.append("f:" + ",".join(sorted(self.frameworks)))
        if self.capabilities:
            parts.append("p:" + ",".join(sorted(self.capabilities)))
        if self.artifact_types:
            parts.append("a:" + ",".join(sorted(self.artifact_types)))
        if self.requirements:
            parts.append("r:" + ",".join(sorted(self.requirements)))
        return "|".join(parts)

    def __hash__(self) -> int:
        return hash(self.context_key())


@dataclass
class WorkflowInstance:
    """A single workflow run recorded for learning purposes."""

    workflow_id: str = field(
        default_factory=lambda: f"wf_{uuid.uuid4().hex[:12]}"
    )
    template_id: str = ""
    template_version: int = 1
    fingerprint: WorkflowFingerprint | None = None
    status: str = "PENDING"
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class WorkflowOutcome:
    """The recorded result of a completed workflow run."""

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
    provider_summary: list = field(default_factory=list)
    activity_graph_id: str | None = None

    @property
    def fingerprint_key(self) -> str:
        if self.fingerprint is None:
            return ""
        return self.fingerprint.context_key()


# Fallback walk: (task_type, languages, frameworks, project_size) masks.
# A non-zero mask component keeps that dimension; zero drops it.
# Most specific first, generic (all dropped) last.
_FINGERPRINT_FALLBACK_CHAIN: list[tuple[int, int, int, int]] = [
    (4, 3, 2, 1),
    (4, 3, 2, 0),
    (4, 3, 0, 0),
    (4, 0, 0, 0),
    (0, 0, 0, 0),
]


def _clean_list(value: str) -> list[str]:
    if not value:
        return []
    return sorted(
        item.strip() for item in value.split(",") if item and item.strip()
    )


def _fingerprint_fallback_key(
    task_type: str = "",
    languages: str = "",
    frameworks: str = "",
    project_size: str = "",
) -> str:
    """Build a partial fingerprint key in the same format as context_key()."""
    parts: list[str] = []
    if task_type and task_type.strip():
        parts.append(f"t:{task_type.strip()}")
    langs = _clean_list(languages)
    if langs:
        parts.append("l:" + ",".join(langs))
    fws = _clean_list(frameworks)
    if fws:
        parts.append("f:" + ",".join(fws))
    if project_size and project_size.strip():
        parts.append(f"s:{project_size.strip()}")
    return "|".join(parts)


def _parse_fingerprint_key(key: str) -> dict:
    """Parse a fingerprint key into the four fallback dimensions.

    Returns exactly: task_type, languages, frameworks, project_size
    (all strings). Segments outside the fallback dimensions (c:, p:,
    a:, r:) are ignored.
    """
    parsed = {
        "task_type": "",
        "languages": "",
        "frameworks": "",
        "project_size": "",
    }
    if not key:
        return parsed
    for segment in key.split("|"):
        if ":" not in segment:
            continue
        prefix, value = segment.split(":", 1)
        if not value:
            continue
        if prefix == "t":
            parsed["task_type"] = value
        elif prefix == "l":
            parsed["languages"] = value
        elif prefix == "f":
            parsed["frameworks"] = value
        elif prefix == "s":
            parsed["project_size"] = value
    return parsed
