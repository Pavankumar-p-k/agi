"""Dynamic replanning engine for multi-provider orchestration.

Completed from the committed contract in tests/unit/test_orchestration.py
(TestAdaptEngine).  Strategy ladder, each rung tried once:

  alternative provider → capability substitution → abort

No infinite retry loops: the orchestrator bounds total attempts per step.
"""
from __future__ import annotations

import logging
from enum import IntEnum
from typing import Any, Optional
from uuid import uuid4

from core.providers.orchestration.models import (
    OrchestrationPlan,
    ProviderStep,
    StepConfidence,
    StepDependency,
)

logger = logging.getLogger(__name__)

__all__ = ["ReplanLevel", "AdaptEngine", "_RELATED_CAPABILITIES"]


class ReplanLevel(IntEnum):
    ABORT = 0
    RETRY = 1
    ALTERNATIVE_PROVIDER = 2
    SUBSTITUTED_CAPABILITY = 3
    ALTERNATIVE_WORKFLOW = 4


# Capabilities considered interchangeable when the requested one is unavailable.
_RELATED_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "coding": ("testing", "review", "documentation"),
    "review": ("testing", "security", "documentation"),
    "testing": ("coding", "review"),
    "security": ("testing", "review"),
    "documentation": ("coding", "review"),
    "research": ("coding",),
}


class AdaptEngine:
    """Bounded replanning: alternative provider, then capability substitution."""

    def _registry(self) -> Any:
        try:
            from core.providers.registry import provider_registry
            return provider_registry
        except Exception as exc:
            logger.debug("[adapt] registry unavailable: %s", exc)
            return None

    def find_alternative(
        self,
        step: ProviderStep,
        exclude_providers: Optional[set[str]] = None,
    ) -> Optional[Any]:
        """Find a live provider (≠ the step's own) able to run the step."""
        capability = str((step.task or {}).get("capability", "") or "")
        exclude = set(exclude_providers or set())
        exclude.add(step.provider_id)
        registry = self._registry()
        if registry is None or not capability:
            return None
        try:
            candidates = [
                p
                for p in registry.get_providers_for_capability(capability)
                if p.provider_id not in exclude and p.enabled
            ]
            if not candidates:
                # Last resort: any other enabled provider.
                candidates = [
                    p for p in registry.list_enabled() if p.provider_id not in exclude
                ]
            if not candidates:
                return None
            candidates.sort(
                key=lambda p: (registry.get_priority(p.provider_id), p.provider_id)
            )
            return candidates[0]
        except Exception as exc:
            logger.debug("[adapt] find_alternative failed: %s", exc)
            return None

    def find_capability_substitution(
        self, step: ProviderStep
    ) -> Optional[tuple[str, Any]]:
        """(related capability, provider) when the requested capability is unavailable."""
        requested = str((step.task or {}).get("capability", "") or "")
        if not requested:
            return None
        registry = self._registry()
        if registry is None:
            return None
        for related in _RELATED_CAPABILITIES.get(requested, ()):
            try:
                providers = [
                    p for p in registry.get_providers_for_capability(related) if p.enabled
                ]
            except Exception:
                continue
            if providers:
                try:
                    providers.sort(
                        key=lambda p: (registry.get_priority(p.provider_id), p.provider_id)
                    )
                except Exception:
                    pass
                return related, providers[0]
        return None

    def create_replan(
        self,
        plan: OrchestrationPlan,
        step: ProviderStep,
        reason: str,
        attempted_providers: Optional[set[str]] = None,
    ) -> tuple[ReplanLevel, Optional[ProviderStep]]:
        """Build the next replan attempt for a failed step (never mutates ``plan``)."""
        exclude = set(attempted_providers or set())
        exclude.add(step.provider_id)

        alternative = self.find_alternative(step, exclude_providers=exclude)
        if alternative is not None:
            return ReplanLevel.ALTERNATIVE_PROVIDER, self._clone_step(
                step,
                provider_id=str(alternative.provider_id),
            )

        substitution = self.find_capability_substitution(step)
        if substitution is not None and substitution[1].provider_id not in exclude:
            capability, provider = substitution
            new_step = self._clone_step(step, provider_id=str(provider.provider_id))
            new_step.task = dict(new_step.task)
            new_step.task["capability"] = capability
            return ReplanLevel.SUBSTITUTED_CAPABILITY, new_step

        logger.info(
            "[adapt] no replan available for step %s (%s)",
            step.step_id,
            reason,
        )
        return ReplanLevel.ABORT, None

    def _clone_step(self, step: ProviderStep, provider_id: str) -> ProviderStep:
        """Copy a step under a fresh, collision-free id for the retry."""
        base = f"{step.step_id}_r{uuid4().hex[:6]}"
        return ProviderStep(
            step_id=base,
            task=dict(step.task),
            chain_type=step.chain_type,
            provider_id=provider_id,
            label=step.label,
            dependencies=[StepDependency(step_id=d.step_id) for d in step.dependencies],
            max_retries=step.max_retries,
            timeout=step.timeout,
        )

    def compute_confidence(
        self,
        success: bool,
        retries: int,
        duration_ms: float,
        quality_score: float = 0.0,
        cost: float = 0.0,
        replan_level: Optional[ReplanLevel] = None,
    ) -> StepConfidence:
        """Confidence/risk for one step outcome (deterministic, bounded)."""
        if not success:
            return StepConfidence(
                confidence=0.0,
                quality_score=float(quality_score or 0.0),
                cost=float(cost or 0.0),
                risk=1.0,
            )
        safe_duration = max(0.0, float(duration_ms or 0.0))
        confidence = 0.95 - 0.05 * max(0, int(retries)) - min(0.1, safe_duration / 60000.0)
        risk = 0.05 + 0.02 * max(0, int(retries)) + min(0.15, safe_duration / 40000.0)
        if replan_level is not None:
            risk += 0.10
            confidence -= 0.02
        return StepConfidence(
            confidence=max(0.0, min(1.0, confidence)),
            quality_score=float(quality_score or 0.0),
            cost=float(cost or 0.0),
            risk=max(0.0, min(1.0, risk)),
        )
