from __future__ import annotations

import logging
from typing import Any

from .ProviderDecisionMatrix import ProviderDecisionMatrix
from .ProviderStrategicMemory import ProviderStrategicMemory
from .ProviderTrustRegistry import ProviderTrustRegistry
from .provider_health_registry import ProviderHealthRegistry
from .runtime.config import JarvisConfig
from .runtime.exceptions import GovernanceViolation

logger = logging.getLogger(__name__)


class RuntimeGovernanceLayer:
    def __init__(
        self,
        trust_registry: ProviderTrustRegistry,
        health_registry: ProviderHealthRegistry,
        decision_matrix: ProviderDecisionMatrix,
        strategic_memory: ProviderStrategicMemory,
        config: JarvisConfig,
    ) -> None:
        self.trust_registry = trust_registry
        self.health_registry = health_registry
        self.decision_matrix = decision_matrix
        self.strategic_memory = strategic_memory
        self.config = config
        self.privacy_ceiling = 0.4
        self.cost_threshold = 0.25
        self.trust_floor = 0.35
        self.hallucination_threshold = 0.7

    def _policy_compliant(self, provider_status: dict[str, Any], task_profile: dict[str, Any]) -> bool:
        provider_name = provider_status.get("provider", "").lower()
        if task_profile["privacy_sensitive"] and provider_name == "rest":
            return False
        if task_profile.get("offline_only") and provider_name == "rest":
            return False
        if task_profile.get("offline_only") and provider_name not in {"fallback", "ollama"}:
            return False
        if task_profile["cost_sensitive"] and provider_name == "rest":
            return False
        return True

    def _is_sensitive_task(self, task_profile: dict[str, Any], task: str) -> bool:
        if task_profile.get("privacy_sensitive") or task_profile.get("offline_only"):
            return True
        normalized = task.lower()
        sensitive_tokens = (
            "finance",
            "bank",
            "medical",
            "health",
            "diagnosis",
            "legal",
            "identity",
            "passport",
            "credential",
            "password",
            "ssn",
            "social security",
            "root",
            "admin",
        )
        return any(token in normalized for token in sensitive_tokens)

    def _identity_concordance(self, provider_name: str, task_profile: dict[str, Any]) -> bool:
        trust = self.trust_registry.get_trust(provider_name)
        if trust < self.trust_floor:
            return False
        if task_profile["privacy_sensitive"] and provider_name.lower() == "rest":
            return False
        return True

    def _governance_safe(self, decision: dict[str, Any], task_profile: dict[str, Any]) -> bool:
        if decision.get("governance_risk", 1.0) > self.hallucination_threshold:
            return False
        if decision.get("trustworthiness", 0.0) < self.trust_floor:
            return False
        if task_profile["privacy_sensitive"] and decision.get("privacy", 0.0) < self.privacy_ceiling:
            return False
        if task_profile.get("offline_only") and decision.get("offline_availability", 0.0) < 0.7:
            return False
        return True

    def authorize(self, provider_name: str, provider_status: dict[str, Any], task_profile: dict[str, Any], decision: dict[str, Any]) -> bool:
        compliant = self._policy_compliant(provider_status, task_profile)
        identity_safe = self._identity_concordance(provider_name, task_profile)
        governance_safe = self._governance_safe(decision, task_profile)
        allowed = compliant and identity_safe and governance_safe
        if not allowed:
            raise GovernanceViolation(
                f"Governance authorization denied for provider {provider_name}: "
                f"compliant={compliant} identity_safe={identity_safe} governance_safe={governance_safe}"
            )
        return True

    def finalize_selection(self, candidate_statuses: dict[str, dict[str, Any]], task: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        task_profile = self.decision_matrix.evaluate_task(task, options)
        ranked = self.decision_matrix.rank_all(candidate_statuses, task, options)
        sensitive_task = self._is_sensitive_task(task_profile, task)

        if task_profile.get("offline_only"):
            fallback_name = next((name for name, status in candidate_statuses.items() if name == "fallback" and status.get("ready", False)), None)
            if fallback_name:
                fallback_decision = self.decision_matrix.score_provider(fallback_name, candidate_statuses[fallback_name], task_profile)
                if self.authorize(fallback_name, candidate_statuses[fallback_name], task_profile, fallback_decision):
                    logger.debug("Offline-only governance selected fallback for task %s.", task)
                    return {"provider": fallback_name, "decision": fallback_decision, "task_profile": task_profile}
            offline_candidates = [candidate for candidate in ranked if candidate.get("offline_availability", 0.0) >= 0.7 and candidate.get("provider") != "rest"]
            for candidate in offline_candidates:
                provider_name = candidate["provider"]
                status = candidate_statuses.get(provider_name, {})
                try:
                    if self.authorize(provider_name, status, task_profile, candidate):
                        logger.debug("Offline-only governance selected %s for task %s.", provider_name, task)
                        return {"provider": provider_name, "decision": candidate, "task_profile": task_profile}
                except GovernanceViolation:
                    continue
            raise GovernanceViolation("Offline-only task had no compliant provider.")
        if task_profile["privacy_sensitive"]:
            fallback_name = next((name for name, status in candidate_statuses.items() if name == "fallback" and status.get("ready", False)), None)
            if fallback_name:
                fallback_decision = self.decision_matrix.score_provider(fallback_name, candidate_statuses[fallback_name], task_profile)
                if self.authorize(fallback_name, candidate_statuses[fallback_name], task_profile, fallback_decision):
                    logger.debug("Privacy-sensitive governance selected fallback for task %s.", task)
                    return {"provider": fallback_name, "decision": fallback_decision, "task_profile": task_profile}
            privacy_candidates = [candidate for candidate in ranked if candidate.get("privacy", 0.0) >= 0.95 or candidate.get("offline_availability", 0.0) >= 0.9]
            for candidate in privacy_candidates:
                provider_name = candidate["provider"]
                status = candidate_statuses.get(provider_name, {})
                try:
                    if self.authorize(provider_name, status, task_profile, candidate):
                        logger.debug("Privacy-sensitive governance selected %s for task %s.", provider_name, task)
                        return {"provider": provider_name, "decision": candidate, "task_profile": task_profile}
                except GovernanceViolation:
                    continue
            raise GovernanceViolation("Privacy-sensitive task had no compliant provider.")

        for candidate in ranked:
            provider_name = candidate["provider"]
            status = candidate_statuses.get(provider_name, {})
            try:
                if self.authorize(provider_name, status, task_profile, candidate):
                    return {"provider": provider_name, "decision": candidate, "task_profile": task_profile}
            except GovernanceViolation:
                continue
        fallback = next((name for name, status in candidate_statuses.items() if name == "fallback" and status.get("ready", False)), None)
        if fallback:
            decision = self.decision_matrix.score_provider(fallback, candidate_statuses[fallback], task_profile)
            return {"provider": fallback, "decision": decision, "task_profile": task_profile}
        if sensitive_task:
            raise GovernanceViolation("Sensitive task blocked: no governance-compliant provider could be selected.")
        raise RuntimeError("No governance-compliant provider could be selected.")
