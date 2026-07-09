"""PolicyOptimizationStage — closes the learning-to-policy feedback loop.

Consumes ``LearningRecord`` (from the Learning stage) and produces
``PolicyOptimizationResult`` with suggested policy adjustments (profile
selection, rate limit multipliers, capability filtering hints).

Pipeline position: after Learning, before Memory (Sprint 6).
"""
from __future__ import annotations

from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.policy_optimization_result import PolicyOptimizationResult


class PolicyOptimizationStage(PipelineStage):
    """Canonical policy optimization stage.

    Analyzes learning records and produces policy optimization signals
    that downstream stages (Memory) persist for cross-request policy
    adaptation.
    """

    @property
    def name(self) -> str:
        return "policy_optimization"

    async def execute(self, context: PipelineContext) -> StageResult:
        records = context.learning_records

        if not records:
            context.policy_optimization_result = None
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # ── Aggregate learning signals ──────────────────────────────────
        success_ratings = [r.success_rating for r in records]
        confidences = [r.confidence for r in records]
        all_patterns: set[str] = set()
        for r in records:
            for p in r.patterns:
                all_patterns.add(p)
        total_contradictions = sum(r.contradictions for r in records)

        avg_success = sum(success_ratings) / len(success_ratings) if success_ratings else 0.0
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # ── Derive optimization signals ─────────────────────────────────
        opt = PolicyOptimizationResult(
            optimization_id=_make_optimization_id(context.services),
            activity_id=records[0].activity_id,
            suggested_profile=_suggest_profile(avg_success, avg_confidence, total_contradictions),
            rate_limit_multiplier=_suggest_rate_limit_mult(avg_success, avg_confidence),
            adjusted_risk_max=_suggest_risk_max(avg_success, avg_confidence),
            allow_patterns=tuple(sorted(all_patterns)) if avg_success >= 0.6 else (),
            block_patterns=tuple(sorted(all_patterns)) if avg_success < 0.3 else (),
            confidence=avg_confidence,
        )

        context.policy_optimization_result = opt
        if opt.suggested_profile is not None:
            context.policy_profile = opt.suggested_profile

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


def _make_optimization_id(services: Any) -> str:
    """Generate a deterministic or random optimization id."""
    raw = services.uuid4()
    if isinstance(raw, str):
        return f"opt_{raw[:24]}"
    return f"opt_{raw.hex[:24]}"


def _suggest_profile(
    avg_success: float,
    avg_confidence: float,
    contradictions: int,
) -> str | None:
    """Suggest a ``PolicyProfile`` based on learning signals."""
    if avg_success >= 0.8 and avg_confidence >= 0.7 and contradictions == 0:
        return "autonomous"
    if avg_success >= 0.6 and avg_confidence >= 0.5 and contradictions <= 1:
        return "developer"
    if avg_success < 0.4 or contradictions >= 3:
        return "strict"
    return None


def _suggest_rate_limit_mult(avg_success: float, avg_confidence: float) -> float:
    """Suggest a rate limit multiplier."""
    if avg_success >= 0.8 and avg_confidence >= 0.7:
        return 2.0
    if avg_success >= 0.6 and avg_confidence >= 0.5:
        return 1.5
    if avg_success < 0.4:
        return 0.5
    return 1.0


def _suggest_risk_max(avg_success: float, avg_confidence: float) -> str | None:
    """Suggest a max risk level adjustment."""
    if avg_success >= 0.9 and avg_confidence >= 0.8:
        return "critical"
    if avg_success >= 0.7 and avg_confidence >= 0.6:
        return "high"
    if avg_success < 0.4:
        return "low"
    return None
