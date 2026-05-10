"""Stage Pruner - Phase 7 Mythos Omega.

Implements stage selection based on priorities.
NEVER removes reasoning stage (audit requirement).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Stages that are NEVER removed (critical for system function)
CRITICAL_STAGES = {"classify", "plan", "execute"}


class StagePruner:
    """
    Prunes stages based on priorities and budget constraints.
    NEVER removes critical stages (reasoning pipeline).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._min_stages = self.config.get("min_stages", 3)
        self._pruning_aggressiveness = self.config.get("pruning_aggressiveness", 0.5)

    def prune(
        self,
        stages: List[str],
        plan: Any,
        cost_estimate: Optional[Any] = None,
        latency_estimate: Optional[Any] = None,
    ) -> List[str]:
        """
        Prune stages based on:
        1. Grounding priority (keep if high)
        2. Verification priority (keep if high)
        3. Cost constraints (remove expensive if over budget)
        4. Latency constraints (remove slow if over threshold)
        """
        if not stages:
            return stages

        # Always keep critical stages
        pruned = [s for s in stages if s in CRITICAL_STAGES]
        optional_stages = [s for s in stages if s not in CRITICAL_STAGES]

        # Score each optional stage
        scored_stages = []
        for stage in optional_stages:
            score = self._score_stage(stage, plan, cost_estimate, latency_estimate)
            scored_stages.append((stage, score))

        # Sort by score (highest first)
        scored_stages.sort(key=lambda x: x[1], reverse=True)

        # Add stages while respecting constraints
        for stage, score in scored_stages:
            # Always include high-value stages
            if score > 0.7:
                pruned.append(stage)
            # Include medium-value stages if not too many stages
            elif score > 0.4 and len(pruned) < 6:
                pruned.append(stage)
            # Low-value stages only if very few stages
            elif len(pruned) < self._min_stages:
                pruned.append(stage)
            else:
                logger.info("Pruned stage: %s (score=%.2f)", stage, score)

        # Ensure minimum stages
        if len(pruned) < self._min_stages:
            for stage, score in scored_stages:
                if stage not in pruned:
                    pruned.append(stage)
                    if len(pruned) >= self._min_stages:
                        break

        # Maintain original order (critical stages first, then optional in order)
        ordered = []
        for stage in stages:
            if stage in pruned and stage not in ordered:
                ordered.append(stage)

        return ordered

    def _score_stage(
        self,
        stage: str,
        plan: Any,
        cost_estimate: Optional[Any] = None,
        latency_estimate: Optional[Any] = None,
    ) -> float:
        """Score a stage based on its value."""
        score = 0.5  # baseline

        # Grounding stage
        if stage == "grounding":
            grounding_priority = getattr(plan, "grounding_priority", 0.5)
            score = grounding_priority
            # Boost if verification priority is also high (they work together)
            verification_priority = getattr(plan, "verification_priority", 0.5)
            if verification_priority > 0.6:
                score += 0.2

        # Verification stage
        elif stage == "adversarial_verification":
            verification_priority = getattr(plan, "verification_priority", 0.5)
            score = verification_priority
            # Boost if contradiction detected
            if hasattr(plan, "contradiction_detected") and plan.contradiction_detected:
                score = min(1.0, score + 0.3)

        # Calibration stage
        elif stage == "calibrate":
            score = 0.8  # Always valuable
            # Boost if uncertainty is high
            uncertainty = getattr(plan, "uncertainty_score", 0.5)
            if uncertainty > 0.6:
                score += 0.2

        # Cost estimation
        elif stage == "cost_estimation":
            score = 0.6  # Important for budget management

        # Budget adjustment
        elif stage == "adjust_budget":
            score = 0.5  # Only needed if over budget

        # Prune stages (meta-stage)
        elif stage == "prune_stages":
            score = 0.3  # Lower priority

        # Apply cost penalty
        if cost_estimate and stage in getattr(cost_estimate, "breakdown", {}):
            stage_cost = cost_estimate.breakdown[stage]
            total_cost = cost_estimate.total_cost
            if total_cost > 0:
                cost_ratio = stage_cost / total_cost
                if cost_ratio > 0.3:  # Stage is expensive
                    score -= cost_ratio * 0.5

        # Apply latency penalty
        if latency_estimate and stage in getattr(latency_estimate, "breakdown", {}):
            stage_latency = latency_estimate.breakdown[stage]
            total_latency = latency_estimate.total_latency_ms
            if total_latency > 0:
                latency_ratio = stage_latency / total_latency
                if latency_ratio > 0.3:  # Stage is slow
                    score -= latency_ratio * 0.5

        return max(0.0, min(1.0, score))

    def get_pruning_report(self, original: List[str], pruned: List[str]) -> Dict[str, Any]:
        """Generate report of what was pruned."""
        removed = [s for s in original if s not in pruned]
        return {
            "original_count": len(original),
            "pruned_count": len(pruned),
            "removed_stages": removed,
            "kept_stages": pruned,
            "removal_count": len(removed),
        }
