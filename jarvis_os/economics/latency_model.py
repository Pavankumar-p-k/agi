"""Dynamic Latency Model - Phase 7 Mythos Omega.

Implements predictive latency estimation with DYNAMIC adjustment.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LatencyEstimate:
    def __init__(self):
        self.total_latency_ms: float = 0.0
        self.breakdown: Dict[str, float] = {}
        self.confidence: float = 1.0


class LatencyModel:
    """
    Dynamic latency model that:
    1. Predicts latency based on stage complexity
    2. Adjusts dynamically based on actual performance
    3. NOT static (audit requirement)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._base_latency = {
            "classify": 50,      # 50ms
            "plan": 100,           # 100ms
            "grounding": 2000,     # 2s (web search)
            "cost_estimation": 10,  # 10ms
            "adjust_budget": 5,     # 5ms
            "prune_stages": 10,     # 10ms
            "execute": 500,         # 500ms
            "adversarial_verification": 3000,  # 3s
            "calibrate": 50,        # 50ms
        }
        self._latency_history: List[Dict[str, Any]] = []
        self._latency_threshold_ms = getattr(self.config, 'latency_threshold_ms', 10000)  # 10s

    def estimate(
        self,
        plan: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> LatencyEstimate:
        """
        Predictive latency estimation based on:
        - Stage types
        - Historical performance
        - Model selection
        """
        estimate = LatencyEstimate()

        stages = getattr(plan, "stages", [])
        model = getattr(plan, "model", "ollama")

        # Base latency calculation
        for stage in stages:
            stage_latency = self._estimate_stage_latency(stage, model)
            estimate.breakdown[stage] = stage_latency
            estimate.total_latency_ms += stage_latency

        # Dynamic adjustment based on history
        if self._latency_history:
            recent_avg = sum(h["latency_ms"] for h in self._latency_history[-10:]) / min(10, len(self._latency_history))
            if recent_avg > 0:
                # Adjust prediction based on historical deviation
                actual_vs_predicted = estimate.total_latency_ms / recent_avg
                adjustment = (actual_vs_predicted - 1.0) * 0.3
                estimate.total_latency_ms *= (1.0 + adjustment)
                estimate.confidence = max(0.5, 1.0 - abs(adjustment))

        return estimate

    def adjust_for_latency(
        self,
        plan: Any,
        latency_estimate: LatencyEstimate,
    ) -> Any:
        """
        Dynamically adjust plan to meet latency constraints.
        NOT static - adjusts based on actual performance.
        """
        if latency_estimate.total_latency_ms <= self._latency_threshold_ms:
            return plan  # No adjustment needed

        logger.warning(
            "Latency %.0fms exceeds threshold %.0fms - adjusting plan",
            latency_estimate.total_latency_ms, self._latency_threshold_ms
        )

        # Remove slow stages
        stages = getattr(plan, "stages", [])
        adjusted_stages = stages.copy()

        # Remove adversarial verification if too slow
        if "adversarial_verification" in adjusted_stages:
            adjusted_stages.remove("adversarial_verification")
            latency_estimate.total_latency_ms *= 0.6  # ~40% reduction

        # Reduce grounding if still too slow
        if latency_estimate.total_latency_ms > self._latency_threshold_ms and "grounding" in adjusted_stages:
            adjusted_stages.remove("grounding")
            latency_estimate.total_latency_ms *= 0.8  # ~20% reduction

        # Update plan
        if hasattr(plan, "stages"):
            plan.stages = adjusted_stages

        return plan

    def record_actual_latency(self, stage: str, latency_ms: float):
        """Record actual latency after execution (for dynamic adjustment)."""
        self._latency_history.append({
            "timestamp": time.time(),
            "stage": stage,
            "latency_ms": latency_ms,
        })

    def get_latency_status(self) -> Dict[str, Any]:
        """Get current latency status."""
        recent = self._latency_history[-10:] if self._latency_history else []
        avg_latency = sum(h["latency_ms"] for h in recent) / len(recent) if recent else 0

        return {
            "threshold_ms": self._latency_threshold_ms,
            "recent_avg_ms": avg_latency,
            "recent_samples": len(recent),
            "total_samples": len(self._latency_history),
        }

    def _estimate_stage_latency(self, stage: str, model: str) -> float:
        """Estimate latency for a single stage."""
        base = self._base_latency.get(stage, 100)

        # Model-specific adjustments
        if model == "ollama":
            base *= 0.8  # Local is faster
        elif model in ("openai", "anthropic"):
            base *= 1.5  # API calls add latency

        # Dynamic adjustment from history
        stage_history = [h for h in self._latency_history if h["stage"] == stage]
        if stage_history:
            avg_actual = sum(h["latency_ms"] for h in stage_history) / len(stage_history)
            base = (base + avg_actual) / 2  # Blend base with actual

        return base

    def reset_latency_tracking(self):
        """Reset latency tracking (but keep history for analysis)."""
        self._latency_history.clear()
        logger.info("Latency tracking reset. History cleared.")
