from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from core.providers.base import ExecutionProvider
from core.providers.orchestration.models import (
    ChainType, OrchestrationPlan, ProviderStep, StepDependency,
)
from core.providers.registry import provider_registry
from core.providers.router import provider_router

logger = logging.getLogger(__name__)


class ReplanLevel(Enum):
    """Escalation levels for dynamic replanning on step failure."""

    SAME_PROVIDER_RETRY = 0
    """Retry with same provider (handled by retry logic)."""

    ALTERNATIVE_PROVIDER = 1
    """Try a different provider for the same capability."""

    DIFFERENT_CAPABILITY = 2
    """Use a different capability that can produce the same result."""

    SIMPLIFIED_TASK = 3
    """Run a simpler version of the step that's more likely to succeed."""

    ABORT = 4
    """No recovery possible — fail the plan."""


_CAPABILITY_SUBSTITUTIONS: dict[str, list[str]] = {
    "coding": ["coding"],
    "testing": ["testing", "coding"],
    "security": ["security", "review"],
    "review": ["review", "security"],
    "documentation": ["documentation", "coding"],
    "debugging": ["debugging", "coding"],
    "research": ["research", "coding"],
}

_SIMPLIFIED_TASK_OVERRIDES: dict[str, dict[str, Any]] = {
    "testing": {"goal": "Run basic tests", "mode": "test"},
    "security": {"goal": "Quick security scan", "mode": "audit"},
    "documentation": {"goal": "Generate minimal docs", "mode": "document"},
}


class AdaptEngine:
    """Handles dynamic replanning and capability substitution during execution.

    When a step fails, the AdaptEngine tries escalating recovery strategies:
      1. Alternative provider for same capability
      2. Different capability that can produce equivalent results
      3. Simplified task with reduced expectations
      4. Abort the plan
    """

    def __init__(
        self,
        registry=provider_registry,
        router=provider_router,
    ):
        self._registry = registry
        self._router = router

    def find_alternative(
        self,
        step: ProviderStep,
        exclude_providers: set[str] | None = None,
    ) -> ExecutionProvider | None:
        """Find an alternative provider for this step's capability,
        excluding the specified providers."""
        exclude = exclude_providers or set()
        exclude.add(step.provider_id)
        fallbacks = self._router.select_with_fallback(
            step.task.get("capability", "coding"),
            step.task,
            exclude=exclude,
        )
        return fallbacks[0] if fallbacks else None

    def find_capability_substitution(
        self,
        step: ProviderStep,
        exclude_providers: set[str] | None = None,
    ) -> tuple[str, ExecutionProvider] | None:
        """Find a different capability that can substitute for this step's
        original capability, and a provider that supports it."""
        original_cap = step.task.get("capability", "coding")
        alternatives = _CAPABILITY_SUBSTITUTIONS.get(original_cap, [original_cap])

        exclude = exclude_providers or set()

        for alt_cap in alternatives:
            if alt_cap == original_cap:
                continue
            providers = self._registry.get_providers_for_capability(alt_cap)
            for p in providers:
                if p.provider_id not in exclude and p.enabled:
                    logger.info(
                        "[AdaptEngine] Substituting capability %s → %s via %s",
                        original_cap, alt_cap, p.provider_id,
                    )
                    return alt_cap, p
        return None

    def create_replan(
        self,
        plan: OrchestrationPlan,
        failed_step: ProviderStep,
        failed_result_error: str,
        attempted_providers: set[str] | None = None,
    ) -> tuple[ReplanLevel, ProviderStep | None]:
        """Create a replanned step based on the failure analysis.

        Returns (level, new_step_or_None):
          - (ALTERNATIVE_PROVIDER, step) → retry with new provider
          - (DIFFERENT_CAPABILITY, step) → retry with new capability + provider
          - (SIMPLIFIED_TASK, step) → retry with simplified task
          - (ABORT, None) → cannot recover
        """
        exclude = attempted_providers or {failed_step.provider_id}

        # Level 1: Try alternative provider
        alt = self.find_alternative(failed_step, exclude_providers=exclude)
        if alt:
            new_step = ProviderStep(
                step_id=f"{failed_step.step_id}_retry_{alt.provider_id}",
                chain_type=failed_step.chain_type,
                label=f"{failed_step.label} (via {alt.provider_id})",
                task=dict(failed_step.task),
                provider_id=alt.provider_id,
                dependencies=failed_step.dependencies,
                expected_artifact_keys=failed_step.expected_artifact_keys,
                timeout=failed_step.timeout,
                max_retries=failed_step.max_retries,
            )
            logger.info(
                "[AdaptEngine] Replan step %s → %s (alternative provider: %s)",
                failed_step.step_id, new_step.step_id, alt.provider_id,
            )
            return ReplanLevel.ALTERNATIVE_PROVIDER, new_step

        # Level 2: Try capability substitution
        sub = self.find_capability_substitution(failed_step, exclude_providers=exclude)
        if sub:
            alt_cap, alt_provider = sub
            new_task = dict(failed_step.task)
            new_task["capability"] = alt_cap
            new_task["original_capability"] = failed_step.task.get("capability", "coding")
            new_step = ProviderStep(
                step_id=f"{failed_step.step_id}_sub_{alt_provider.provider_id}",
                chain_type=failed_step.chain_type,
                label=f"{failed_step.label} (as {alt_cap} via {alt_provider.provider_id})",
                task=new_task,
                provider_id=alt_provider.provider_id,
                dependencies=failed_step.dependencies,
                expected_artifact_keys=[],
                timeout=failed_step.timeout,
                max_retries=1,
            )
            logger.info(
                "[AdaptEngine] Replan step %s → %s (capability substitution: %s → %s via %s)",
                failed_step.step_id, new_step.step_id,
                failed_step.task.get("capability", "?"), alt_cap, alt_provider.provider_id,
            )
            return ReplanLevel.DIFFERENT_CAPABILITY, new_step

        # Level 3: Simplified task
        capability = failed_step.task.get("capability", "")
        override = _SIMPLIFIED_TASK_OVERRIDES.get(capability)
        if override:
            new_task = dict(failed_step.task)
            new_task.update(override)
            new_step = ProviderStep(
                step_id=f"{failed_step.step_id}_simplified",
                chain_type=ChainType.SEQUENTIAL,
                label=f"{failed_step.label} (simplified)",
                task=new_task,
                provider_id=failed_step.provider_id,
                dependencies=failed_step.dependencies,
                expected_artifact_keys=[],
                timeout=failed_step.timeout,
                max_retries=1,
            )
            logger.info(
                "[AdaptEngine] Replan step %s → simplified task",
                failed_step.step_id,
            )
            return ReplanLevel.SIMPLIFIED_TASK, new_step

        # Level 4: Abort
        logger.warning(
            "[AdaptEngine] No recovery for step %s (%s)",
            failed_step.step_id, failed_result_error,
        )
        return ReplanLevel.ABORT, None

    def compute_confidence(
        self,
        success: bool,
        retries: int,
        duration_ms: float,
        quality_score: float = 0.0,
        cost: float = 0.0,
        replan_level: ReplanLevel | None = None,
    ) -> "StepConfidence":
        """Compute step confidence from execution metrics.

        Confidence decreases with retries, replanning escalation, and
        long durations. Quality score comes from output analysis.
        """
        from core.providers.orchestration.models import StepConfidence

        base_confidence = 1.0 if success else 0.0

        if success:
            ded = retries * 0.1 + (replan_level.value * 0.15 if replan_level else 0.0)
            confidence = max(0.0, min(1.0, base_confidence - ded))
            risk = retries * 0.1 + (duration_ms / 300000) * 0.2
        else:
            confidence = 0.0
            risk = 1.0

        if replan_level:
            risk += replan_level.value * 0.1

        return StepConfidence(
            confidence=max(0.0, min(1.0, confidence)),
            quality_score=max(0.0, min(1.0, quality_score)),
            cost=max(0.0, cost),
            risk=max(0.0, min(1.0, risk)),
        )
