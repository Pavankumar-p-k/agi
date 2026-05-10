from __future__ import annotations

import logging
from typing import Any

from .ProviderStrategicMemory import ProviderStrategicMemory
from .ProviderTrustRegistry import ProviderTrustRegistry

logger = logging.getLogger(__name__)


class ProviderDecisionMatrix:
    def __init__(
        self,
        config: Any,
        trust_registry: ProviderTrustRegistry,
        strategic_memory: ProviderStrategicMemory,
    ) -> None:
        self.config = config
        self.trust_registry = trust_registry
        self.strategic_memory = strategic_memory
        self.last_decision: dict[str, Any] = {}

    def evaluate_task(self, task: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        normalized = task.lower()
        profile = {
            "task_type": "chat",
            "reasoning_depth": 0.4,
            "latency_sensitivity": 0.5,
            "privacy_sensitive": bool(options.get("privacy_sensitive", False) or "private" in normalized or "sensitive" in normalized),
            "offline_only": bool(options.get("offline_only", False)),
            "cost_sensitive": bool(options.get("cost_sensitive", False) or "cheap" in normalized or "budget" in normalized),
            "coding_strength": 0.0,
            "autonomy_support": 0.0,
            "multimodal_need": 0.0,
            "historical_success_focus": 0.4,
        }
        if any(token in normalized for token in ("reason", "analysis", "strategy", "deep")):
            profile.update({"task_type": "deep_reasoning", "reasoning_depth": 0.92, "latency_sensitivity": 0.3, "historical_success_focus": 0.5})
        if any(token in normalized for token in ("code", "program", "script", "developer", "execute")):
            profile.update({"task_type": "coding", "coding_strength": 0.95, "reasoning_depth": 0.7, "latency_sensitivity": 0.6, "autonomy_support": 0.7})
        if any(token in normalized for token in ("private", "sensitive", "confidential", "secret", "financial", "bank", "account", "credit card", "ssn", "social security", "medical", "health", "doctor", "diagnosis", "legal", "lawyer", "contract", "passport", "identity")):
            profile.update({"task_type": "privacy_critical", "privacy_sensitive": True, "offline_only": True, "latency_sensitivity": 0.4, "cost_sensitive": True})
        if any(token in normalized for token in ("quick", "fast", "cheap", "low cost")):
            profile.update({"task_type": "cheap", "cost_sensitive": True, "latency_sensitivity": 0.8, "reasoning_depth": 0.3})
        if any(token in normalized for token in ("long context", "context", "document", "conversation")):
            profile.update({"task_type": "long_context", "reasoning_depth": 0.65, "latency_sensitivity": 0.5})
        return profile

    def trust_weight(self) -> float:
        return 0.2

    def cost_weight(self) -> float:
        return 0.16

    def privacy_weight(self) -> float:
        return 0.18

    def strategic_weight(self) -> float:
        return 0.18

    def cognitive_weight(self) -> float:
        return 0.16

    def _provider_capabilities(self, provider_name: str, provider_status: dict[str, Any]) -> dict[str, float]:
        base = provider_name.lower()
        capabilities = {
            "reasoning_depth": 0.4,
            "latency": 0.5,
            "privacy": 0.5,
            "trustworthiness": self.trust_registry.get_trust(provider_name),
            "hallucination_risk": 0.5,
            "cost": 0.5,
            "context_window": 0.5,
            "coding_strength": 0.4,
            "autonomy_support": 0.4,
            "multimodal_support": 0.4,
            "offline_availability": 0.0,
            "historical_success": 0.5,
            "regret_score": 0.0,
            "identity_alignment": 0.5,
            "governance_risk": 0.5,
        }
        if base == "ollama":
            capabilities.update({
                "reasoning_depth": 0.75,
                "latency": 0.6,
                "privacy": 0.8,
                "hallucination_risk": 0.42,
                "cost": 0.65,
                "context_window": 0.7,
                "coding_strength": 0.6,
                "autonomy_support": 0.7,
                "multimodal_support": 0.6,
                "offline_availability": 0.75,
                "identity_alignment": 0.8,
                "governance_risk": 0.3,
            })
        elif base == "rest":
            capabilities.update({
                "reasoning_depth": 0.68,
                "latency": 0.45,
                "privacy": 0.35,
                "hallucination_risk": 0.52,
                "cost": 0.55,
                "context_window": 0.7,
                "coding_strength": 0.72,
                "autonomy_support": 0.6,
                "multimodal_support": 0.55,
                "offline_availability": 0.0,
                "identity_alignment": 0.45,
                "governance_risk": 0.55,
            })
        elif base == "fallback":
            capabilities.update({
                "reasoning_depth": 0.28,
                "latency": 0.78,
                "privacy": 1.0,
                "hallucination_risk": 0.22,
                "cost": 0.95,
                "context_window": 0.35,
                "coding_strength": 0.25,
                "autonomy_support": 0.3,
                "multimodal_support": 0.25,
                "offline_availability": 1.0,
                "identity_alignment": 1.0,
                "governance_risk": 0.1,
            })
        models = provider_status.get("models", [])
        if any("code" in str(model).lower() for model in models):
            capabilities["coding_strength"] = max(capabilities["coding_strength"], 0.85)
        if any("reason" in str(model).lower() or "analysis" in str(model).lower() for model in models):
            capabilities["reasoning_depth"] = max(capabilities["reasoning_depth"], 0.85)
        if provider_status.get("base_url") and provider_name.lower() == "rest":
            capabilities["privacy"] = min(0.45, capabilities["privacy"])
        if provider_status.get("provider") == "fallback":
            capabilities["hallucination_risk"] = min(capabilities["hallucination_risk"], 0.2)
        capabilities["historical_success"] = self.strategic_memory.aggregate_scores(provider_name).get("success_rate", 0.5)
        capabilities["regret_score"] = 1.0 - self.trust_registry.get_trust(provider_name)
        return capabilities

    def score_provider(self, provider_name: str, provider_status: dict[str, Any], task_profile: dict[str, Any]) -> dict[str, Any]:
        capabilities = self._provider_capabilities(provider_name, provider_status)
        privacy_weight = self.privacy_weight() * (1.5 if task_profile["privacy_sensitive"] else 1.0)
        cost_weight = self.cost_weight() * (1.3 if task_profile["cost_sensitive"] else 1.0)
        reasoning_factor = task_profile["reasoning_depth"] * capabilities["reasoning_depth"]
        coding_factor = task_profile["coding_strength"] * capabilities["coding_strength"]
        trust_factor = capabilities["trustworthiness"] * self.trust_weight()
        privacy_factor = capabilities["privacy"] * privacy_weight
        cost_factor = capabilities["cost"] * cost_weight
        strategic_factor = capabilities["historical_success"] * self.strategic_weight()
        cognition_factor = (capabilities["context_window"] + capabilities["autonomy_support"] + capabilities["multimodal_support"]) / 3.0 * self.cognitive_weight()
        governance_penalty = max(0.0, 1.0 - capabilities["governance_risk"]) * 0.1
        raw_score = reasoning_factor + coding_factor + trust_factor + privacy_factor + cost_factor + strategic_factor + cognition_factor + governance_penalty
        score = max(0.0, min(1.0, raw_score / 4.5))
        explanation = {
            "provider": provider_name,
            "task_type": task_profile["task_type"],
            "reasoning_depth": capabilities["reasoning_depth"],
            "coding_strength": capabilities["coding_strength"],
            "trustworthiness": capabilities["trustworthiness"],
            "privacy": capabilities["privacy"],
            "cost": capabilities["cost"],
            "governance_risk": capabilities["governance_risk"],
            "score": score,
        }
        logger.debug("Scored provider %s: %s", provider_name, explanation)
        return {"provider": provider_name, "score": score, "explanation": explanation, **capabilities}

    def rank_all(self, candidate_statuses: dict[str, dict[str, Any]], task: str, options: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        task_profile = self.evaluate_task(task, options)
        scored = [self.score_provider(name, status, task_profile) for name, status in candidate_statuses.items() if status.get("ready", False)]
        ranked = sorted(scored, key=lambda item: item["score"], reverse=True)
        self.last_decision = {"task": task, "profile": task_profile, "ranked": ranked}
        return ranked

    def compare_candidates(self, candidate_statuses: dict[str, dict[str, Any]], task: str, options: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self.rank_all(candidate_statuses, task, options)

    def select_best_provider(self, candidate_statuses: dict[str, dict[str, Any]], task: str, options: dict[str, Any] | None = None) -> str:
        ranked = self.rank_all(candidate_statuses, task, options)
        best = ranked[0] if ranked else {}
        return best.get("provider", "")

    def explain_decision(self) -> dict[str, Any]:
        return dict(self.last_decision)
