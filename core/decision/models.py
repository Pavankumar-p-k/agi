from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceDimension:
    """One dimension of evidence for a candidate workflow.

    Each dimension captures a distinct signal that contributes to
    the unified score. Examples: workflow_success, provider_quality,
    system_health, budget_viability.
    """

    name: str
    score: float = 0.0
    weight: float = 0.0
    reason: str = ""
    confidence: float = 0.0
    source: str = ""


@dataclass
class CandidateEvidence:
    """All evidence collected for one candidate workflow template."""

    template_id: str = ""
    template_version: int = 1
    dimensions: list[EvidenceDimension] = field(default_factory=list)
    fingerprint_key: str = ""
    collected_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedScore:
    """Scored decision with full traceability.

    Contains the final score plus every dimension that contributed,
    enabling automated debugging and human-readable explainability.
    """

    template_id: str = ""
    template_version: int = 1
    final_score: float = 0.0
    dimensions: list[EvidenceDimension] = field(default_factory=list)
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


@dataclass
class DecisionResult:
    """Result of selecting the best workflow from candidates."""

    selected: UnifiedScore | None = None
    alternatives: list[UnifiedScore] = field(default_factory=list)
    total_candidates: int = 0
    elapsed_ms: float = 0.0
