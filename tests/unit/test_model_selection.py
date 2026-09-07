import pytest

from core.providers.base import ExecutionProvider, ProviderCapabilities, ProviderHealth, ProviderHealthStatus, ExecutionResult
from core.providers.registry import ProviderRegistry
from core.providers.router import ProviderRouter


class HealthyProvider(ExecutionProvider):
    provider_id = "ollama"

    def capabilities(self):
        return ProviderCapabilities(capability_names=["chat"])

    async def health(self):
        return ProviderHealth(status=ProviderHealthStatus.HEALTHY)

    async def execute(self, task, context=None):
        return ExecutionResult(success=True, output=task["model"])


@pytest.mark.asyncio
async def test_chat_provider_selection_works_in_running_loop():
    registry = ProviderRegistry()
    provider = HealthyProvider()
    registry.register(provider)
    router = ProviderRouter(registry=registry)

    assert router.select("chat", task={"model": "ollama/custom:latest"}) is provider


def test_provider_health_exposes_discovered_models():
    health = ProviderHealth(
        status=ProviderHealthStatus.HEALTHY,
        models_available=["llama3:8b"],
    )
    assert health.models_available == ["llama3:8b"]
