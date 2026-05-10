from __future__ import annotations

import logging
from typing import Any

from .ProviderDecisionMatrix import ProviderDecisionMatrix
from .ProviderStrategicMemory import ProviderStrategicMemory
from .ProviderTrustRegistry import ProviderTrustRegistry

logger = logging.getLogger(__name__)


class ProviderSimulationEngine:
    def __init__(
        self,
        trust_registry: ProviderTrustRegistry,
        strategic_memory: ProviderStrategicMemory,
        decision_matrix: ProviderDecisionMatrix | None = None,
    ) -> None:
        self.trust_registry = trust_registry
        self.strategic_memory = strategic_memory
        self.decision_matrix = decision_matrix

    def simulate_provider(self, provider_name: str, provider_status: dict[str, Any], task_profile: dict[str, Any]) -> dict[str, Any]:
        trust = self.trust_registry.get_trust(provider_name)
        history = self.strategic_memory.aggregate_scores(provider_name)
        privacy_factor = 1.0 if provider_status.get("provider") == "fallback" or provider_status.get("provider") == "ollama" else 0.35
        latency = 0.85 if provider_status.get("provider") == "fallback" else 0.55 if provider_status.get("provider") == "ollama" else 0.45
        if task_profile["privacy_sensitive"] and provider_status.get("provider") == "rest":
            privacy_factor = 0.2
        expected_quality = (
            task_profile["reasoning_depth"] * provider_status.get("reasoning_depth", 0.5)
            + task_profile["coding_strength"] * provider_status.get("coding_strength", 0.4)
            + trust * 0.15
            + history.get("success_rate", 0.5) * 0.1
        ) / 2.0
        strategic_fit = min(1.0, trust * 0.3 + privacy_factor * 0.3 + history.get("average_strategic_value", 0.5) * 0.3)
        risk = 1.0 - privacy_factor
        simulation = {
            "provider": provider_name,
            "expected_quality": expected_quality,
            "expected_latency": 1.0 - latency,
            "expected_trust": trust,
            "expected_privacy": privacy_factor,
            "expected_risk": risk,
            "strategic_fit": strategic_fit,
        }
        logger.debug("Simulated provider %s: %s", provider_name, simulation)
        return simulation

    def simulate_all(self, candidate_statuses: dict[str, dict[str, Any]], task_profile: dict[str, Any]) -> list[dict[str, Any]]:
        results = []
        for provider_name, status in candidate_statuses.items():
            results.append(self.simulate_provider(provider_name, status, task_profile))
        return results
