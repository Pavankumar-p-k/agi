"""Provider feedback models: decision records, outcomes, calibration entries.

Completed from the committed contract in tests/unit/test_provider_feedback.py
(models section) plus tests/unit/test_provider_fallback.py (``ProviderResult``
consumed by ``ProviderMemory.record``).

Pieces:
- ``ProviderResult`` — what a provider reports after one execution.
- ``ScoreBreakdown`` — one candidate provider's routing score components.
- ``RoutingDecision`` — which provider was selected for a task, with the full
  candidate score list (recorded BEFORE execution for later calibration).
- ``RoutingOutcome`` — what actually happened (recorded AFTER execution) with
  a composite ``outcome_score``.
- ``CalibrationEntry`` — a learned per-(provider, capability, context)
  adjustment with confidence and evidence count.
- ``CalibrationConfig`` — tuning knobs (half-life, evidence thresholds).
- ``context_key`` / ``_extract_context`` / ``_CONTEXT_FALLBACK_CHAIN`` —
  context (language/framework/project_size) handling with the specific→generic
  fallback ordering used by the store and calibrator.
- ``_compute_time_weights`` — exponential time-decay weights with hard
  filtering of outcomes older than ``maximum_history_days``.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# ProviderResult (consumed by core.providers.memory.ProviderMemory.record)    #
# --------------------------------------------------------------------------- #

@dataclass
class ProviderResult:
    """Outcome of one provider execution, reported back for learning."""

    provider_id: str = ""
    capability: str = ""
    success: bool = False
    duration_ms: float = 0.0
    error: Optional[str] = None
    metrics: dict[str, Any] = field(default_factory=dict)
    tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "capability": self.capability,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "metrics": dict(self.metrics),
            "tokens": int(self.tokens),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderResult":
        return cls(
            provider_id=data.get("provider_id", ""),
            capability=data.get("capability", ""),
            success=bool(data.get("success", False)),
            duration_ms=float(data.get("duration_ms", 0.0) or 0.0),
            error=data.get("error"),
            metrics=data.get("metrics", {}) or {},
            tokens=int(data.get("tokens", 0) or 0),
        )


# --------------------------------------------------------------------------- #
# ScoreBreakdown                                                              #
# --------------------------------------------------------------------------- #

@dataclass
class ScoreBreakdown:
    """Component scores for one candidate provider at routing time."""

    provider_id: str = ""
    priority_score: float = 0.0
    historical_score: float = 0.0
    benchmark_score: float = 0.0
    calibration_adjustment: float = 0.0
    total_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "priority_score": float(self.priority_score),
            "historical_score": float(self.historical_score),
            "benchmark_score": float(self.benchmark_score),
            "calibration_adjustment": float(self.calibration_adjustment),
            "total_score": float(self.total_score),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoreBreakdown":
        return cls(
            provider_id=str(data.get("provider_id", "") or ""),
            priority_score=float(data.get("priority_score", 0.0) or 0.0),
            historical_score=float(data.get("historical_score", 0.0) or 0.0),
            benchmark_score=float(data.get("benchmark_score", 0.0) or 0.0),
            calibration_adjustment=float(data.get("calibration_adjustment", 0.0) or 0.0),
            total_score=float(data.get("total_score", 0.0) or 0.0),
        )


# --------------------------------------------------------------------------- #
# RoutingDecision / RoutingOutcome                                            #
# --------------------------------------------------------------------------- #

def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class RoutingDecision:
    """Which provider was selected for a task (recorded before execution)."""

    decision_id: str = field(default_factory=lambda: _new_id("dec"))
    goal: str = ""
    capability: str = ""
    task: dict[str, Any] = field(default_factory=dict)
    selected_provider: str = ""
    candidate_scores: list[ScoreBreakdown] = field(default_factory=list)
    excluded_providers: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    # Context convenience properties (task carries language/framework/...) ---
    @property
    def language(self) -> str:
        return str(self.task.get("language", "") or "")

    @property
    def framework(self) -> str:
        return str(self.task.get("framework", "") or "")

    @property
    def project_size(self) -> str:
        return str(self.task.get("project_size", "") or "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "goal": self.goal,
            "capability": self.capability,
            "task": dict(self.task),
            "selected_provider": self.selected_provider,
            "candidate_scores": [c.to_dict() for c in self.candidate_scores],
            "excluded_providers": list(self.excluded_providers),
            "timestamp": float(self.timestamp),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoutingDecision":
        return cls(
            decision_id=str(data.get("decision_id", "") or _new_id("dec")),
            goal=str(data.get("goal", "") or ""),
            capability=str(data.get("capability", "") or ""),
            task=data.get("task", {}) or {},
            selected_provider=str(data.get("selected_provider", "") or ""),
            candidate_scores=[
                c if isinstance(c, ScoreBreakdown) else ScoreBreakdown.from_dict(c)
                for c in (data.get("candidate_scores", []) or [])
            ],
            excluded_providers=list(data.get("excluded_providers", []) or []),
            timestamp=float(data.get("timestamp", time.time()) or 0.0),
        )


@dataclass
class RoutingOutcome:
    """What actually happened after a routing decision (recorded after execution)."""

    outcome_id: str = field(default_factory=lambda: _new_id("out"))
    decision_id: str = ""
    success: bool = False
    duration_ms: float = 0.0
    quality_score: float = 0.0
    cost: float = 0.0
    retries: int = 0
    replan_level: int = 0
    timestamp: float = field(default_factory=time.time)

    @property
    def outcome_score(self) -> float:
        """Composite 0..1 score: quality × duration factor × replan factor.

        Failed outcomes score near zero (0.1 × quality); the default (empty)
        outcome scores exactly 0.0.
        """
        if not self.success:
            return round(0.1 * max(0.0, self.quality_score), 4)
        if self.duration_ms <= 1000.0:
            duration_factor = 1.0
        else:
            duration_factor = max(0.3, 1.0 / (1.0 + self.duration_ms / 600_000.0))
        replan_factor = 1.0 / (1.0 + max(0, self.replan_level))
        return round(max(0.0, self.quality_score) * duration_factor * replan_factor, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "decision_id": self.decision_id,
            "success": bool(self.success),
            "duration_ms": float(self.duration_ms),
            "quality_score": float(self.quality_score),
            "cost": float(self.cost),
            "retries": int(self.retries),
            "replan_level": int(self.replan_level),
            "timestamp": float(self.timestamp),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoutingOutcome":
        return cls(
            outcome_id=str(data.get("outcome_id", "") or _new_id("out")),
            decision_id=str(data.get("decision_id", "") or ""),
            success=bool(data.get("success", False)),
            duration_ms=float(data.get("duration_ms", 0.0) or 0.0),
            quality_score=float(data.get("quality_score", 0.0) or 0.0),
            cost=float(data.get("cost", 0.0) or 0.0),
            retries=int(data.get("retries", 0) or 0),
            replan_level=int(data.get("replan_level", 0) or 0),
            timestamp=float(data.get("timestamp", time.time()) or 0.0),
        )


# --------------------------------------------------------------------------- #
# Calibration entries + context handling                                      #
# --------------------------------------------------------------------------- #

@dataclass
class CalibrationEntry:
    """Learned adjustment for one (provider, capability, context) cell."""

    entry_id: str = field(default_factory=lambda: _new_id("cal"))
    provider_id: str = ""
    capability: str = ""
    adjustment: float = 0.0
    confidence: float = 0.0
    evidence_count: int = 0
    last_updated: float = field(default_factory=time.time)
    language: str = ""
    framework: str = ""
    project_size: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "provider_id": self.provider_id,
            "capability": self.capability,
            "adjustment": float(self.adjustment),
            "confidence": float(self.confidence),
            "evidence_count": int(self.evidence_count),
            "last_updated": float(self.last_updated),
            "language": self.language,
            "framework": self.framework,
            "project_size": self.project_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalibrationEntry":
        return cls(
            entry_id=str(data.get("entry_id", "") or _new_id("cal")),
            provider_id=str(data.get("provider_id", "") or ""),
            capability=str(data.get("capability", "") or ""),
            adjustment=float(data.get("adjustment", 0.0) or 0.0),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            evidence_count=int(data.get("evidence_count", 0) or 0),
            last_updated=float(data.get("last_updated", time.time()) or 0.0),
            language=str(data.get("language", "") or ""),
            framework=str(data.get("framework", "") or ""),
            project_size=str(data.get("project_size", "") or ""),
        )


@dataclass
class CalibrationConfig:
    """Tuning knobs for the calibration engine."""

    half_life_days: float = 100.0
    minimum_weight: float = 0.05
    maximum_history_days: int = 365
    min_evidence: int = 3
    max_evidence: int = 50
    alpha: float = 0.3


def context_key(
    capability: str,
    language: str = "",
    framework: str = "",
    project_size: str = "",
) -> tuple[str, str, str, str]:
    """Canonical context key: (capability, language, framework, project_size)."""
    return (capability, language, framework, project_size)


def _extract_context(task: Optional[dict[str, Any]]) -> dict[str, str]:
    """Pull (language, framework, project_size) from a task dict, defaulting to ""."""
    task = task or {}
    return {
        "language": str(task.get("language", "") or ""),
        "framework": str(task.get("framework", "") or ""),
        "project_size": str(task.get("project_size", "") or ""),
    }


# Ordered specific→generic context fallback patterns over
# (language, framework, project_size).  Nonzero = keep that field in the
# lookup, 0 = drop to wildcard.  Index 0 (3,2,1) keeps all three; the last
# (0,0,0) is the fully generic entry.
_CONTEXT_FALLBACK_CHAIN: list[tuple[int, int, int]] = [
    (3, 2, 1),  # language + framework + project_size (most specific)
    (2, 1, 0),  # language + framework
    (1, 0, 0),  # language only
    (0, 0, 0),  # generic
]


def _compute_time_weights(
    timestamps: list[float],
    half_life_days: float = 100.0,
    max_history_days: int = 365,
    min_weight: float = 0.05,
    now: Optional[float] = None,
) -> tuple[list[float], float]:
    """Exponential time-decay weights for outcome timestamps.

    - Weight = 0.5 ** (age_days / half_life_days).
    - Outcomes older than ``max_history_days`` are dropped entirely.
    - Future timestamps clamp to age 0 (weight 1.0).
    - Returns (weights aligned to kept timestamps, effective_n = sum(weights)).
    """
    if now is None:
        now = time.time()
    weights: list[float] = []
    for ts in timestamps:
        age_days = max(0.0, (now - float(ts)) / 86400.0)
        if age_days > max_history_days:
            continue
        if half_life_days > 0:
            w = 0.5 ** (age_days / half_life_days)
        else:
            w = 1.0
        if w < min_weight:
            continue
        weights.append(w)
    return weights, sum(weights)
