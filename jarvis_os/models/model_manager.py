from __future__ import annotations

from typing import Any

from .base import ModelProvider, ModelRequest


class ModelManager:
    def __init__(
        self,
        router: ModelProvider,
        *,
        providers: dict[str, ModelProvider] | None = None,
        default_provider: str = "",
    ) -> None:
        from ..model_runtime_manager import ModelRuntimeManager
        from ..provider_health_registry import ProviderHealthRegistry

        self.router = router
        self.providers = dict(providers or {})
        if router.name not in self.providers:
            self.providers[router.name] = router
        self.default_provider = default_provider or router.name
        self.health_registry = ProviderHealthRegistry(self.providers)
        self.runtime = ModelRuntimeManager(
            providers=self.providers,
            default_provider=self.default_provider,
            health_registry=self.health_registry,
        )

    def status(self) -> dict[str, Any]:
        status = self.runtime.status()
        active_provider = status.get("provider")
        if active_provider is not None:
            status["active_provider"] = active_provider
        return status

    def route(self, task: str, provider: str = "") -> dict[str, Any]:
        return self.runtime.route(task)

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
        return self.runtime.generate(
            prompt,
            task,
            system,
            options=options,
            model=model,
            provider=provider,
        )

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
        return self.runtime.stream(
            prompt,
            task,
            system,
            options=options,
            model=model,
            provider=provider,
        )

    def _provider(self, name: str = "") -> ModelProvider:
        return self.runtime._provider(name)
