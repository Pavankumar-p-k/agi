"""Dynamic Cost Model - Phase 7 Mythos Omega.

Implements predictive cost estimation with DYNAMIC adjustment (NOT static).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CostEstimate:
    def __init__(self):
        self.total_cost: float = 0.0
        self.breakdown: Dict[str, float] = {}
        self.confidence: float = 1.0
        self.adjusted: bool = False


class CostModel:
    """
    Dynamic cost model that:
    1. Predicts costs based on task complexity and model selection
    2. Adjusts dynamically based on budget constraints
    3. NOT static (audit requirement)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._cost_per_token = {
            "ollama": 0.0,        # Local = free
            "rest": 0.002,         # ~$2 per 1M tokens
            "openai": 0.03,        # ~$30 per 1M tokens
            "anthropic": 0.025,     # ~$25 per 1M tokens
            "google": 0.0015,       # ~$1.5 per 1M tokens
        }
        self._cost_history: List[Dict[str, Any]] = []
        self._budget_limit = getattr(self.config, 'budget_limit', 10.0)  # $10 default
        self._current_spend = 0.0

    def estimate(
        self,
        plan: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> CostEstimate:
        """
        Predictive cost estimation based on:
        - Number of tokens (input + estimated output)
        - Model selection
        - Number of stages
        - Verification depth
        """
        estimate = CostEstimate()

        # Get plan details
        num_stages = len(getattr(plan, "stages", []))
        model = getattr(plan, "model", "ollama")
        avg_tokens_per_stage = self._estimate_tokens(plan, context)

        # Base cost calculation
        for stage in getattr(plan, "stages", []):
            stage_cost = self._cost_per_token.get(model, 0.01) * avg_tokens_per_stage
            estimate.breakdown[stage] = stage_cost
            estimate.total_cost += stage_cost

        # Additional costs for special stages
        if hasattr(plan, "grounding_priority") and plan.grounding_priority > 0.5:
            # Grounding uses web search APIs
            estimate.total_cost += 0.01 * estimate.total_cost
            estimate.breakdown["grounding"] = 0.01 * estimate.total_cost

        if hasattr(plan, "verification_priority") and plan.verification_priority > 0.5:
            # Verification uses additional model calls
            verification_cost = estimate.total_cost * 0.5
            estimate.total_cost += verification_cost
            estimate.breakdown["verification"] = verification_cost

        # Dynamic adjustment based on history
        if self._cost_history:
            recent_avg = sum(h["cost"] for h in self._cost_history[-10:]) / min(10, len(self._cost_history))
            if recent_avg > 0:
                # Adjust prediction based on historical deviation
                adjustment = (estimate.total_cost / recent_avg - 1.0) * 0.2
                estimate.total_cost *= (1.0 + adjustment)
                estimate.adjusted = True

        # Record estimate
        self._cost_history.append({
            "timestamp": time.time(),
            "cost": estimate.total_cost,
            "type": "estimate",
        })

        return estimate

    def adjust_for_budget(
        self,
        plan: Any,
        cost_estimate: CostEstimate,
        available_budget: Optional[float] = None,
    ) -> Any:
        """
        Dynamically adjust plan based on budget constraints.
        NOT static - adjusts based on actual spend and remaining budget.
        """
        budget = available_budget or (self._budget_limit - self._current_spend)

        if cost_estimate.total_cost <= budget:
            return plan  # No adjustment needed

        # Need to reduce cost
        logger.warning(
            "Cost %.3f exceeds budget %.3f - adjusting plan",
            cost_estimate.total_cost, budget
        )

        # Dynamic adjustment: remove expensive stages
        stages = getattr(plan, "stages", [])
        adjusted_stages = stages.copy()

        # Remove verification first (most expensive)
        if "adversarial_verification" in adjusted_stages:
            adjusted_stages.remove("adversarial_verification")
            cost_estimate.total_cost *= 0.7  # ~30% reduction

        # Reduce grounding if still over budget
        if cost_estimate.total_cost > budget and "grounding" in adjusted_stages:
            adjusted_stages.remove("grounding")
            cost_estimate.total_cost *= 0.85  # ~15% reduction

        # Update plan
        if hasattr(plan, "stages"):
            plan.stages = adjusted_stages

        return plan

    def record_actual_cost(self, cost: float, stage: str = "unknown"):
        """Record actual cost after execution (for dynamic adjustment)."""
        self._current_spend += cost
        self._cost_history.append({
            "timestamp": time.time(),
            "cost": cost,
            "type": "actual",
            "stage": stage,
        })

    def get_budget_status(self) -> Dict[str, Any]:
        """Get current budget status."""
        return {
            "budget_limit": self._budget_limit,
            "current_spend": self._current_spend,
            "remaining": self._budget_limit - self._current_spend,
            "percent_used": (self._current_spend / self._budget_limit * 100) if self._budget_limit > 0 else 0,
        }

    def _estimate_tokens(self, plan: Any, context: Optional[Dict[str, Any]]) -> float:
        """Estimate average tokens per stage."""
        base_tokens = 500  # Base tokens per stage

        # Adjust based on task type
        task_type = getattr(plan, "task_type", "general")
        if task_type == "complex_reasoning":
            base_tokens = 2000
        elif task_type == "coding":
            base_tokens = 1500
        elif task_type == "factual_query":
            base_tokens = 800

        # Adjust based on complexity
        if hasattr(plan, "complexity_score"):
            base_tokens *= (1.0 + plan.complexity_score)

        return base_tokens

    def reset_budget(self, new_limit: Optional[float] = None):
        """Reset budget (but keep history for dynamic adjustment)."""
        if new_limit is not None:
            self._budget_limit = new_limit
        self._current_spend = 0.0
        logger.info("Budget reset. New limit: %.2f", self._budget_limit)
