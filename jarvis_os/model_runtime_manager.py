from __future__ import annotations

import logging
from typing import Any

from .ProviderDecisionMatrix import ProviderDecisionMatrix
from .ProviderRegretEngine import ProviderRegretEngine

from .ProviderStrategicMemory import ProviderStrategicMemory
from .ProviderTrustRegistry import ProviderTrustRegistry
from .RuntimeGovernanceLayer import RuntimeGovernanceLayer
from .models.base import ModelProvider, ModelRequest
from .provider_health_registry import ProviderHealthRegistry
from .runtime.config import JarvisConfig
from .runtime.exceptions import GovernanceViolation, RuntimeBoundaryViolation

logger = logging.getLogger(__name__)


class ModelRuntimeManager:
    name = "model_runtime"

    def __init__(
        self,
        providers: dict[str, ModelProvider],
        default_provider: str = "",
        health_registry: ProviderHealthRegistry | None = None,
        trust_registry: ProviderTrustRegistry | None = None,
        strategic_memory: ProviderStrategicMemory | None = None,
        decision_matrix: ProviderDecisionMatrix | None = None,

        governance_layer: RuntimeGovernanceLayer | None = None,
        config: JarvisConfig | None = None,
    ) -> None:
        self.providers = providers
        self.config = config or JarvisConfig.from_env()
        self.health_registry = health_registry or ProviderHealthRegistry(providers)
        self.trust_registry = trust_registry or ProviderTrustRegistry(providers)
        self.strategic_memory = strategic_memory or ProviderStrategicMemory(self.config)
        self.decision_matrix = decision_matrix or ProviderDecisionMatrix(self.config, self.trust_registry, self.strategic_memory)
        self.regret_engine = ProviderRegretEngine(self.trust_registry, self.strategic_memory)
        self.governance_layer = governance_layer or RuntimeGovernanceLayer(
            self.trust_registry,
            self.health_registry,
            self.decision_matrix,
            self.strategic_memory,
            self.config,
        )
        self.default_provider = default_provider if default_provider in providers else next(iter(providers), "")
        self.active_provider: ModelProvider | None = None
        self.active_provider = self._resolve_active_provider()

    def _update_provider_statuses(self) -> dict[str, dict[str, Any]]:
        statuses: dict[str, dict[str, Any]] = {}
        for name, provider in self.providers.items():
            try:
                status = provider.status()
            except Exception as exc:
                status = {"ready": False, "provider": name, "error": str(exc), "models": []}
            statuses[name] = status
            self.health_registry.update_status(name, status)
            self.trust_registry.register_provider(name)
        return statuses

    def _resolve_active_provider(self) -> ModelProvider:
        statuses = self._update_provider_statuses()
        try:
            selection = self.governance_layer.finalize_selection(statuses, "chat", {})
            return self.providers[selection["provider"]]
        except GovernanceViolation as exc:
            logger.error("Governance blocked active provider resolution: %s", exc)
            raise RuntimeBoundaryViolation(str(exc)) from exc
        except RuntimeError as exc:
            logger.warning("Governance selection unavailable, falling back to decision matrix: %s", exc)
        selected_name = self.decision_matrix.select_best_provider(statuses, "chat", {})
        selected = self.providers.get(selected_name, self.providers.get(self.default_provider, next(iter(self.providers.values()), None)))
        if selected is None:
            raise RuntimeBoundaryViolation("No provider available for runtime manager.")
        return selected

    def _build_task_context(self, task: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.decision_matrix.evaluate_task(task, options)

    def _select_provider(self, provider: str | None, task: str, options: dict[str, Any] | None = None) -> tuple[ModelProvider, dict[str, Any], dict[str, Any]]:
        options = dict(options or {})
        statuses = self._update_provider_statuses()
        task_profile = self._build_task_context(task, options)

        if provider and provider in self.providers:
            selected = self.providers[provider]
            status = statuses.get(provider, {})
            decision = self.decision_matrix.score_provider(provider, status, task_profile)
            if status.get("ready", False) and self.governance_layer.authorize(provider, status, task_profile, decision):
                self.active_provider = selected
                return selected, status, decision
            logger.warning("Explicit provider %s denied by governance or unavailable.", provider)

        selection = self.governance_layer.finalize_selection(statuses, task, options)
        provider_name = selection.get("provider", "")
        selected = self.providers.get(provider_name) or next(iter(self.providers.values()))
        status = statuses.get(provider_name, {})
        decision = selection.get("decision", {})
        self.active_provider = selected
        return selected, status, decision

    def _fallback_provider(self, current_name: str) -> ModelProvider:
        statuses = self._update_provider_statuses()
        fallback_name = next((name for name, status in statuses.items() if name == "fallback" and status.get("ready", False)), None)
        if fallback_name and fallback_name != current_name:
            return self.providers[fallback_name]
        for provider_name in self.health_registry.best_providers():
            if provider_name == current_name:
                continue
            candidate = self.providers.get(provider_name)
            if candidate is None:
                continue
            status = statuses.get(provider_name, {})
            if status.get("ready", False):
                return candidate
        return self.providers.get(current_name, next(iter(self.providers.values())))

    def status(self) -> dict[str, Any]:
        statuses = {name: provider.status() for name, provider in self.providers.items()}
        return {
            "ready": any(status.get("ready", False) for status in statuses.values()),
            "provider": self.active_provider.name if self.active_provider else self.default_provider,
            "providers": statuses,
            "health": self.health_registry.summary(),
            "trust": self.trust_registry.summary(),
        }

    def _record_execution(self, provider_name: str, task: str, request_data: ModelRequest, response: dict[str, Any], status: dict[str, Any], decision: dict[str, Any], fallback: bool) -> None:
        task_profile = self._build_task_context(task, request_data.options)
        candidate_statuses = self._update_provider_statuses()
        metrics = {}
        candidates = []
        regret = self.regret_engine.assess_regret(task_profile["task_type"], provider_name, metrics, response, candidates)
        self.trust_registry.record_outcome(
            provider_name,
            success=bool(response.get("ok", False)),
            hallucination=bool(response.get("error") or response.get("done") is False),
            privacy_ok=not task_profile["privacy_sensitive"] or status.get("provider") != "rest",
            strategic_fit=metrics.get("strategic_fit", 0.5),
            policy_compliant=self.governance_layer._policy_compliant(status, task_profile),
            regret_penalty=regret["trust_penalty"],
        )
        self.strategic_memory.record(
            task_type=task_profile["task_type"],
            provider=provider_name,
            success=bool(response.get("ok", False)),
            regret_score=regret["regret_score"],
            trust_drift=self.trust_registry.get_trust(provider_name) - 0.5,
            latency_ms=int(request_data.options.get("latency_ms", 0) or 0),
            hallucination_incidents=1 if bool(response.get("error") or response.get("done") is False) else 0,
            user_satisfaction=1.0 if bool(response.get("ok", False)) else 0.2,
            correction_cost=float(request_data.options.get("correction_cost", 0.0) or 0.0),
            strategic_value=metrics.get("strategic_fit", 0.5),
            governance_override=fallback,
            privacy_sensitive=task_profile["privacy_sensitive"],
        )

    def generate(
        self,
        prompt: str,
        task: str = "chat",
        system: str = "",
        *,
        options: dict[str, Any] | None = None,
        model: str = "",
        provider: str = "",
    ) -> dict[str, Any]:
        request_data = ModelRequest(
            prompt=prompt,
            task=task,
            system=system,
            options=dict(options or {}),
            model=model,
        )
        selected, status, decision = self._select_provider(provider or None, task, request_data.options)
        response = selected.generate(request_data)
        if response.get("ok", False):
            self.health_registry.report_success(selected.name, status)
            self._record_execution(selected.name, task, request_data, response, status, decision, fallback=False)
            return response

        self.health_registry.report_failure(selected.name, response.get("error", "unknown"))
        fallback_provider = self._fallback_provider(selected.name)
        if fallback_provider.name != selected.name:
            logger.info("Governed failover from %s to %s.", selected.name, fallback_provider.name)
            response = fallback_provider.generate(request_data)
            fallback_status = self.providers[fallback_provider.name].status()
            if response.get("ok", False):
                self.health_registry.report_success(fallback_provider.name, fallback_status)
            self._record_execution(fallback_provider.name, task, request_data, response, fallback_status, decision, fallback=True)
            return response

        self._record_execution(selected.name, task, request_data, response, status, decision, fallback=False)
        return response

    def stream(
        self,
        prompt: str,
        task: str = "chat",
        system: str = "",
        *,
        options: dict[str, Any] | None = None,
        model: str = "",
        provider: str = "",
    ) -> list[dict[str, Any]]:
        request_data = ModelRequest(
            prompt=prompt,
            task=task,
            system=system,
            options=dict(options or {}),
            model=model,
        )
        selected, status, decision = self._select_provider(provider or None, task, request_data.options)
        results = list(selected.stream(request_data))
        if results and results[-1].get("ok", True):
            self.health_registry.report_success(selected.name, status)
            self._record_execution(selected.name, task, request_data, {"ok": True}, status, decision, fallback=False)
            return results

        error_message = results[-1].get("error", "unknown") if results else "no response"
        self.health_registry.report_failure(selected.name, error_message)
        fallback_provider = self._fallback_provider(selected.name)
        if fallback_provider.name != selected.name:
            logger.info("Governed streaming failover from %s to %s.", selected.name, fallback_provider.name)
            results = list(fallback_provider.stream(request_data))
            fallback_status = self.providers[fallback_provider.name].status()
            if results and results[-1].get("ok", True):
                self.health_registry.report_success(fallback_provider.name, fallback_status)
            self._record_execution(fallback_provider.name, task, request_data, {"ok": results and results[-1].get("ok", False)}, fallback_status, decision, fallback=True)
            return results

        self._record_execution(selected.name, task, request_data, {"ok": False, "error": error_message}, status, decision, fallback=False)
        return results

    def _provider(self, name: str | None = None) -> ModelProvider:
        return self._select_provider(name or None, "chat", {})[0]
