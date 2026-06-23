"""core/model_providers/base.py
Abstract base class and shared types for all model providers.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class ProviderStatus:
    available: bool = True
    healthy: bool = True
    latency_ms: float = 0.0
    error: str = ""
    models_available: list[str] = field(default_factory=list)


@dataclass
class ModelResult:
    content: str
    model: str
    provider: str
    latency_ms: float = 0.0
    tokens_used: int = 0
    finish_reason: str = "stop"
    raw: dict[str, Any] | None = None


class ModelProvider(ABC):
    name: str = ""
    default_model: str = ""

    def __init__(self):
        self._models: list[str] = []
        self._base_url: str = ""

    @abstractmethod
    async def generate(self, model: str, messages: list[dict[str, Any]], **kwargs) -> ModelResult:
        ...

    @abstractmethod
    async def stream(self, model: str, messages: list[dict[str, Any]], **kwargs) -> AsyncIterator[str]:
        ...
        yield ""

    @abstractmethod
    async def embeddings(self, model: str, input_text: str | list[str]) -> list[float]:
        ...

    @abstractmethod
    async def vision(self, model: str, messages: list[dict[str, Any]], image_data: str, **kwargs) -> ModelResult:
        ...

    @abstractmethod
    async def health_check(self) -> ProviderStatus:
        ...

    def _get_credentials(self) -> dict[str, str]:
        from core.api_key_vault import vault
        prefix = self.name.upper()
        return {
            "api_key": vault.get(f"{prefix}_API_KEY") or "",
        }

    def set_base_url(self, url: str):
        self._base_url = url

    def get_models(self) -> list[str]:
        return self._models


async def health_check_all() -> dict[str, ProviderStatus]:
    from core.model_providers import (
        OllamaProvider, OpenAIProvider, AnthropicProvider,
        GeminiProvider, GroqProvider, OpenRouterProvider,
    )
    results = {}
    providers = [
        ("ollama", OllamaProvider()),
        ("openai", OpenAIProvider()),
        ("anthropic", AnthropicProvider()),
        ("gemini", GeminiProvider()),
        ("groq", GroqProvider()),
        ("openrouter", OpenRouterProvider()),
    ]
    for name, provider in providers:
        try:
            results[name] = await provider.health_check()
        except Exception as e:
            results[name] = ProviderStatus(available=False, healthy=False, error=str(e))
    return results
