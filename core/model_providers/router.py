"""core/model_providers/router.py
Unified ModelRouter.
Selects provider/model based on task type, latency, cost, user preference, and provider availability.
Supports runtime switching without restart via config_registry.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

from core.model_providers.base import ModelProvider, ModelResult, ProviderStatus
from core.model_providers.ollama import OllamaProvider
from core.model_providers.openai import OpenAIProvider
from core.model_providers.anthropic import AnthropicProvider
from core.model_providers.gemini import GeminiProvider
from core.model_providers.groq import GroqProvider
from core.model_providers.openrouter import OpenRouterProvider


class TaskType(Enum):
    CHAT = "chat"
    CODING = "coding"
    VISION = "vision"
    PLANNING = "planning"
    ANALYSIS = "analysis"
    REASONING = "reasoning"
    EMBEDDINGS = "embeddings"
    CLASSIFIER = "classifier"
    CREATIVE = "creative"
    GRADER = "grader"


@dataclass
class TaskProfile:
    task: TaskType
    primary_provider: str = "local"
    fallback_provider: str = "cloud"
    preferred_model: str = ""
    max_latency_ms: float = 30000.0
    max_cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.value,
            "primary": self.primary_provider,
            "fallback": self.fallback_provider,
            "preferred_model": self.preferred_model,
            "max_latency_ms": self.max_latency_ms,
        }


DEFAULT_TASK_PROFILES: dict[TaskType, TaskProfile] = {
    TaskType.CHAT: TaskProfile(task=TaskType.CHAT, primary_provider="local", fallback_provider="cloud"),
    TaskType.CODING: TaskProfile(task=TaskType.CODING, primary_provider="local", fallback_provider="cloud"),
    TaskType.VISION: TaskProfile(task=TaskType.VISION, primary_provider="local", fallback_provider="cloud"),
    TaskType.PLANNING: TaskProfile(task=TaskType.PLANNING, primary_provider="local", fallback_provider="cloud"),
    TaskType.ANALYSIS: TaskProfile(task=TaskType.ANALYSIS, primary_provider="local", fallback_provider="cloud"),
    TaskType.REASONING: TaskProfile(task=TaskType.REASONING, primary_provider="local", fallback_provider="cloud"),
    TaskType.EMBEDDINGS: TaskProfile(task=TaskType.EMBEDDINGS, primary_provider="local", fallback_provider="cloud"),
    TaskType.CLASSIFIER: TaskProfile(task=TaskType.CLASSIFIER, primary_provider="local", fallback_provider="cloud"),
    TaskType.CREATIVE: TaskProfile(task=TaskType.CREATIVE, primary_provider="local", fallback_provider="cloud"),
    TaskType.GRADER: TaskProfile(task=TaskType.GRADER, primary_provider="local", fallback_provider="cloud"),
}

TASK_TO_ROLE: dict[TaskType, str] = {
    TaskType.CHAT: "chat",
    TaskType.CODING: "code",
    TaskType.VISION: "vision",
    TaskType.PLANNING: "chat",
    TaskType.ANALYSIS: "analysis",
    TaskType.REASONING: "reasoning",
    TaskType.EMBEDDINGS: "chat",
    TaskType.CLASSIFIER: "chat",
    TaskType.CREATIVE: "chat",
    TaskType.GRADER: "grader",
}


PROVIDER_INSTANCES: dict[str, ModelProvider] = {}


def _get_provider(name: str) -> ModelProvider:
    if name not in PROVIDER_INSTANCES:
        providers = {
            "ollama": OllamaProvider(),
            "openai": OpenAIProvider(),
            "anthropic": AnthropicProvider(),
            "gemini": GeminiProvider(),
            "groq": GroqProvider(),
            "openrouter": OpenRouterProvider(),
        }
        PROVIDER_INSTANCES.update(providers)
    return PROVIDER_INSTANCES[name]


class ModelRouter:
    def __init__(self):
        self._profiles: dict[TaskType, TaskProfile] = dict(DEFAULT_TASK_PROFILES)
        self._provider_cache: dict[str, ProviderStatus] = {}
        self._cache_ttl = 30.0
        self._last_cache_update = 0.0

    def get_profile(self, task: TaskType) -> TaskProfile:
        from core.config_registry import config as _cfg
        task_key = task.value
        stored = _cfg.get(f"task_profile.{task_key}", None)
        if stored and isinstance(stored, dict):
            return TaskProfile(
                task=task,
                primary_provider=stored.get("primary", "local"),
                fallback_provider=stored.get("fallback", "cloud"),
                preferred_model=stored.get("preferred_model", ""),
                max_latency_ms=stored.get("max_latency_ms", 30000.0),
            )
        return self._profiles.get(task, DEFAULT_TASK_PROFILES[task])

    def set_profile(self, task: TaskType, profile: TaskProfile):
        self._profiles[task] = profile
        from core.config_registry import config as _cfg
        _cfg.set(f"task_profile.{task.value}", profile.to_dict())

    def set_provider_for_task(self, task: TaskType, provider: str):
        profile = self.get_profile(task)
        profile.primary_provider = provider
        self.set_profile(task, profile)

    def get_available_providers(self) -> dict[str, bool]:
        return {name: status.available for name, status in self._provider_cache.items()}

    async def _refresh_cache(self):
        now = time.time()
        if now - self._last_cache_update < self._cache_ttl:
            return
        for name in ["ollama", "openai", "anthropic", "gemini", "groq", "openrouter"]:
            try:
                provider = _get_provider(name)
                status = await provider.health_check()
                self._provider_cache[name] = status
            except Exception:
                self._provider_cache[name] = ProviderStatus(available=False, healthy=False)
        self._last_cache_update = now

    def _resolve_provider_name(self, preference: str) -> str:
        if preference in ("local", "ollama"):
            return "ollama"
        if preference == "cloud":
            for name in ["openai", "anthropic", "openrouter", "groq", "gemini"]:
                cached = self._provider_cache.get(name)
                if cached and cached.available and cached.healthy:
                    return name
            return "openai"
        return preference

    async def select(self, task: TaskType, preferred_model: str = "") -> tuple[ModelProvider, str]:
        await self._refresh_cache()
        profile = self.get_profile(task)
        model = preferred_model or profile.preferred_model
        primary = self._resolve_provider_name(profile.primary_provider)
        cached = self._provider_cache.get(primary)

        if cached and cached.available and cached.healthy:
            provider = _get_provider(primary)
            actual_model = model or provider.default_model
            return provider, actual_model

        fallback = self._resolve_provider_name(profile.fallback_provider)
        fb_cached = self._provider_cache.get(fallback)
        if fb_cached and fb_cached.available and fb_cached.healthy:
            provider = _get_provider(fallback)
            actual_model = model or provider.default_model
            return provider, actual_model

        return _get_provider("ollama"), "qwen2.5-coder:3b"

    async def generate(self, task: TaskType, messages: list[dict[str, Any]], **kwargs) -> ModelResult:
        provider, model = await self.select(task, kwargs.pop("preferred_model", ""))
        return await provider.generate(model, messages, **kwargs)

    async def stream(self, task: TaskType, messages: list[dict[str, Any]], **kwargs) -> AsyncIterator[str]:
        provider, model = await self.select(task, kwargs.pop("preferred_model", ""))
        async for chunk in provider.stream(model, messages, **kwargs):
            yield chunk

    async def embeddings(self, task: TaskType, input_text: str | list[str], **kwargs) -> list[float]:
        provider, model = await self.select(task)
        return await provider.embeddings(model, input_text)

    async def vision(self, task: TaskType, messages: list[dict[str, Any]], image_data: str, **kwargs) -> ModelResult:
        provider, model = await self.select(task)
        return await provider.vision(model, messages, image_data, **kwargs)

    async def health_check(self) -> dict[str, ProviderStatus]:
        await self._refresh_cache()
        return dict(self._provider_cache)

    def get_task_profiles(self) -> dict[str, dict[str, Any]]:
        return {k.value: v.to_dict() for k, v in self._profiles.items()}


_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
