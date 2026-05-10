from __future__ import annotations

import logging
from typing import Any


from .ProviderStrategicMemory import ProviderStrategicMemory
from .ProviderTrustRegistry import ProviderTrustRegistry

logger = logging.getLogger(__name__)


class ProviderRegretEngine:
    def __init__(
        self,
        trust_registry: ProviderTrustRegistry,
        strategic_memory: ProviderStrategicMemory,
    ) -> None:
        self.trust_registry = trust_registry
        self.strategic_memory = strategic_memory


    def assess_regret(self, task_type: str, selected_provider: str, selected_metrics: dict[str, Any], outcome: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
        success = bool(outcome.get("ok", False))
        hallucination = bool(outcome.get("hallucination", False) or outcome.get("error", "") or outcome.get("done") is False)
        trust_drift = self.trust_registry.get_trust(selected_provider) - 0.5
        selected_quality = selected_metrics.get("expected_quality", 0.5)
        alt_quality = max((candidate.get("expected_quality", 0.5) for candidate in candidates if candidate["provider"] != selected_provider), default=0.5)

        quality_gap = max(0.0, alt_quality - selected_quality)
        regret_base = 0.0
        if not success:
            regret_base += 0.4
        if hallucination:
            regret_base += 0.25
        regret_base += quality_gap * 0.3
        regret_base += max(0.0, 0.3 - trust_drift) * 0.2
        regret_base += float(outcome.get("cost", 0.0)) * 0.1
        regret_score = max(0.0, min(1.0, regret_base))

        rerank_recommendation = None
        if alt_quality > selected_quality + 0.05:
            rerank = sorted(candidates, key=lambda cand: cand.get("expected_quality", 0.0), reverse=True)
            rerank_recommendation = rerank[0]["provider"] if rerank else None

        trust_penalty = regret_score * 0.25
        logger.debug(
            "Regret assessed for provider %s: success=%s, hallucination=%s, quality_gap=%.3f, regret=%s, recommendation=%s",
            selected_provider,
            success,
            hallucination,
            quality_gap,
            regret_score,
            rerank_recommendation,
        )
        return {
            "regret_score": regret_score,
            "trust_penalty": trust_penalty,
            "rerank_recommendation": rerank_recommendation,
            "quality_gap": quality_gap,
        }
