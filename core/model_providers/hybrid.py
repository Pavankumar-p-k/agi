"""core/model_providers/hybrid.py
HybridModelPlatform.
Three user-facing modes:
  - local  → Ollama only
  - cloud  → OpenAI, Gemini, Anthropic, Groq, OpenRouter
  - hybrid → simple tasks → local, complex → cloud, offline → local
Supports runtime switching without restart via config_registry.
Auto-fallback on provider failure — never blocks the user.
"""
from __future__ import annotations

import asyncio
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
from core.model_providers.router import TaskType


class HybridMode(Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


# Simple tasks that are cheap/fast locally
SIMPLE_TASKS = {
    TaskType.CLASSIFIER,
    TaskType.GRADER,
    TaskType.EMBEDDINGS,
    TaskType.CHAT,
}

# Complex tasks that benefit from cloud
COMPLEX_TASKS = {
    TaskType.CODING,
    TaskType.PLANNING,
    TaskType.ANALYSIS,
    TaskType.REASONING,
    TaskType.CREATIVE,
}

# Tasks with preferred providers
PREFERRED_PROVIDERS: dict[TaskType, str] = {
    TaskType.VISION: "openai",
    TaskType.CODING: "anthropic",
    TaskType.REASONING: "anthropic",
}


@dataclass
class ModelInfo:
    """Display model info."""
    provider: str
    model: str
    status: str = "unknown"
    latency_ms: float = 0.0
    cost_estimate: str = "free"
    error: str = ""


LOCAL_COST = "free"
CLOUD_COST: dict[str, str] = {
    "openai": "$0.01-0.03/1K tokens",
    "anthropic": "$0.02-0.05/1K tokens",
    "gemini": "$0.00-0.02/1K tokens",
    "groq": "free tier",
    "openrouter": "varies",
}


class HybridModelPlatform:
    """Top-level model platform with mode switching and auto-fallback."""

    def __init__(self):
        self._providers: dict[str, ModelProvider] = {}
        self._cache: dict[str, ProviderStatus] = {}
        self._cache_ttl = 15.0
        self._last_cache_update = 0.0
        self._init_providers()

    def _init_providers(self):
        for p in [
            ("ollama", OllamaProvider()),
            ("openai", OpenAIProvider()),
            ("anthropic", AnthropicProvider()),
            ("gemini", GeminiProvider()),
            ("groq", GroqProvider()),
            ("openrouter", OpenRouterProvider()),
        ]:
            self._providers[p[0]] = p[1]

    @property
    def mode(self) -> HybridMode:
        from core.config_registry import config as _cfg
        val = _cfg.get("model.mode", "local")
        try:
            return HybridMode(val)
        except ValueError:
            return HybridMode.LOCAL

    @mode.setter
    def mode(self, m: HybridMode):
        from core.config_registry import config as _cfg
        _cfg.set("model.mode", m.value)
        self._invalidate_cache()

    def set_mode_from_string(self, val: str) -> str:
        try:
            m = HybridMode(val.lower())
            self.mode = m
            return f"Switched to {m.value} mode"
        except ValueError:
            return f"Invalid mode: {val}. Choose: local, cloud, hybrid"

    def _invalidate_cache(self):
        self._last_cache_update = 0.0

    async def _refresh_cache(self, force: bool = False):
        now = time.time()
        if not force and now - self._last_cache_update < self._cache_ttl:
            return
        for name, provider in self._providers.items():
            try:
                self._cache[name] = await provider.health_check()
            except Exception:
                self._cache[name] = ProviderStatus(available=False, healthy=False, error="health check failed")
        self._last_cache_update = now

    def _is_available(self, name: str) -> bool:
        cached = self._cache.get(name)
        if cached is None:
            return True
        return cached.available and cached.healthy

    def _pick_for_mode(self, task: TaskType) -> str:
        current_mode = self.mode
        if current_mode == HybridMode.LOCAL:
            return "ollama"

        if current_mode == HybridMode.CLOUD:
            if task in PREFERRED_PROVIDERS:
                preferred = PREFERRED_PROVIDERS[task]
                if self._is_available(preferred):
                    return preferred
            for name in ["openai", "anthropic", "openrouter", "groq", "gemini"]:
                if self._is_available(name):
                    return name
            return "ollama"

        if current_mode == HybridMode.HYBRID:
            if task in COMPLEX_TASKS:
                preferred = PREFERRED_PROVIDERS.get(task, "openai")
                if self._is_available(preferred):
                    return preferred
                for name in ["openai", "anthropic", "openrouter", "groq", "gemini"]:
                    if self._is_available(name):
                        return name
            if self._is_available("ollama"):
                return "ollama"
            if task in COMPLEX_TASKS:
                for name in ["openai", "anthropic", "openrouter", "groq", "gemini"]:
                    if self._is_available(name):
                        return name
            return "ollama"

        return "ollama"

    async def _auto_fallback(self, task: TaskType, model: str, messages: list[dict], kwargs: dict) -> ModelResult:
        last_error = ""
        tried = set()

        for attempt in range(3):
            if attempt == 0:
                provider_name = self._pick_for_mode(task)
            else:
                provider_name = self._next_available(provider_name if attempt > 1 else "", tried)

            if not provider_name or provider_name in tried:
                break
            tried.add(provider_name)
            provider = self._providers.get(provider_name)
            if not provider:
                continue
            try:
                actual_model = model or provider.default_model
                return await provider.generate(actual_model, messages, **kwargs)
            except Exception as e:
                last_error = str(e)
                continue

        return ModelResult(
            content=f"All providers unavailable. Last error: {last_error}",
            model="none", provider="none",
            finish_reason="error",
        )

    def _next_available(self, current: str, tried: set[str]) -> str | None:
        order = ["ollama", "openai", "anthropic", "openrouter", "groq", "gemini"]
        for name in order:
            if name not in tried and self._is_available(name):
                return name
        for name in order:
            if name not in tried:
                return name
        return None

    async def generate(self, task: TaskType, messages: list[dict[str, Any]], **kwargs) -> ModelResult:
        await self._refresh_cache()
        return await self._auto_fallback(task, kwargs.pop("preferred_model", ""), messages, kwargs)

    async def stream(self, task: TaskType, messages: list[dict[str, Any]], **kwargs) -> AsyncIterator[str]:
        await self._refresh_cache()
        provider_name = self._pick_for_mode(task)
        provider = self._providers.get(provider_name)
        if not provider:
            yield "No provider available"
            return
        model = kwargs.pop("preferred_model", "") or provider.default_model
        async for chunk in provider.stream(model, messages, **kwargs):
            yield chunk

    async def embeddings(self, task: TaskType, input_text: str | list[str]) -> list[float]:
        await self._refresh_cache()
        provider_name = self._pick_for_mode(task)
        provider = self._providers.get(provider_name)
        if not provider:
            return []
        return await provider.embeddings(provider.default_model, input_text)

    async def vision(self, task: TaskType, messages: list[dict[str, Any]], image_data: str, **kwargs) -> ModelResult:
        await self._refresh_cache()
        provider_name = self._pick_for_mode(task)
        provider = self._providers.get(provider_name)
        if not provider:
            return ModelResult(content="No provider available", model="none", provider="none", finish_reason="error")
        model = kwargs.pop("preferred_model", "") or provider.default_model
        return await provider.vision(model, messages, image_data, **kwargs)

    async def list_models(self) -> list[ModelInfo]:
        await self._refresh_cache(force=True)
        results = []
        for name, provider in self._providers.items():
            cached = self._cache.get(name, ProviderStatus())
            models = cached.models_available or [provider.default_model]
            for m in models[:3]:
                status = "healthy" if cached.healthy else ("down" if cached.error else "unknown")
                results.append(ModelInfo(
                    provider=name,
                    model=m,
                    status=status,
                    latency_ms=cached.latency_ms,
                    cost_estimate=LOCAL_COST if name == "ollama" else CLOUD_COST.get(name, "unknown"),
                    error=cached.error,
                ))
        return results

    async def test_model(self, provider_name: str = "", model: str = "") -> ModelInfo:
        await self._refresh_cache(force=True)
        targets = [provider_name] if provider_name else list(self._providers.keys())
        results = []
        for name in targets:
            provider = self._providers.get(name)
            if not provider:
                continue
            cached = self._cache.get(name, ProviderStatus())
            actual_model = model or provider.default_model
            try:
                start = time.time()
                result = await provider.generate(actual_model, [
                    {"role": "user", "content": "Reply with exactly one word: OK"}
                ])
                latency = (time.time() - start) * 1000
                status = "healthy" if result.content else "empty_response"
                results.append(ModelInfo(
                    provider=name, model=actual_model,
                    status=status, latency_ms=latency,
                    cost_estimate=LOCAL_COST if name == "ollama" else CLOUD_COST.get(name, "unknown"),
                ))
            except Exception as e:
                results.append(ModelInfo(
                    provider=name, model=actual_model,
                    status="error", error=str(e),
                ))
        return results[0] if results else ModelInfo(provider="none", model="", status="no_providers")

    async def benchmark(self, provider_name: str = "", model: str = "") -> list[dict[str, Any]]:
        await self._refresh_cache(force=True)
        targets = [provider_name] if provider_name else list(self._providers.keys())
        results = []
        for name in targets:
            provider = self._providers.get(name)
            if not provider:
                continue
            cached = self._cache.get(name, ProviderStatus())
            if not cached.available:
                results.append({"provider": name, "status": "unavailable"})
                continue
            actual_model = model or provider.default_model
            bench = {"provider": name, "model": actual_model, "tests": []}
            for test_msg, test_len in [
                ("Reply with exactly one word: OK", "short"),
                ("Write a one-sentence summary of machine learning.", "medium"),
            ]:
                try:
                    start = time.time()
                    result = await provider.generate(actual_model, [
                        {"role": "user", "content": test_msg}
                    ], max_tokens=50, temperature=0.1)
                    latency = (time.time() - start) * 1000
                    bench["tests"].append({
                        "type": test_len,
                        "latency_ms": round(latency, 1),
                        "tokens": result.tokens_used,
                    })
                except Exception as e:
                    bench["tests"].append({
                        "type": test_len,
                        "latency_ms": 0,
                        "error": str(e),
                    })
            results.append(bench)
        return results


_platform: HybridModelPlatform | None = None


def get_platform() -> HybridModelPlatform:
    global _platform
    if _platform is None:
        _platform = HybridModelPlatform()
    return _platform
