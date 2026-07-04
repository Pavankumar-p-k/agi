"""ProviderManager — central API for resolving capabilities to models.

All code should call `ProviderManager.get_best_available(capability)` instead of
hardcoding model names. Wraps ProviderRouter (evidence-based selection),
ConfigurationService (routing preferences), and LLMRouter (LiteLLM dispatch).

Usage:
    from core.providers.manager import provider_manager

    model = provider_manager.get_best_available("chat")
    result = await provider_manager.complete("chat", prompt)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.configuration import configuration as config_service
from core.providers.base import ExecutionProvider
from core.providers.registry import provider_registry
from core.providers.router import ProviderRouter

logger = logging.getLogger(__name__)

CAPABILITY_ALIASES: dict[str, str] = {
    "conversation": "chat",
    "dialogue": "chat",
    "talk": "chat",
    "coding": "code",
    "programming": "code",
    "build": "code",
    "research": "analysis",
    "analyze": "analysis",
    "think": "reasoning",
    "plan": "reasoning",
    "image": "vision",
    "visual": "vision",
    "screen": "vision",
    "grade": "grader",
    "evaluate": "grader",
    "quality": "grader",
    "embed": "embedding",
    "vector": "embedding",
    "route": "orchestrator",
    "orchestrate": "orchestrator",
}


class ProviderManager:
    def __init__(self):
        self._router: ProviderRouter | None = None
        self._resolved_cache: dict[str, str] = {}
        self._cache_valid = False

    @property
    def router(self) -> ProviderRouter:
        if self._router is None:
            self._router = ProviderRouter()
        return self._router

    def invalidate_cache(self):
        self._cache_valid = False
        self._resolved_cache.clear()

    def _normalize_capability(self, capability: str) -> str:
        return CAPABILITY_ALIASES.get(capability, capability)

    def get_best_available(self, capability: str) -> str:
        """Get the best model identifier for a capability.

        Returns a LiteLLM-compatible string like 'ollama/qwen2.5:7b'.
        No model names are hardcoded in callers — this is the single source.
        """
        capability = self._normalize_capability(capability)

        # First: try the evidence-based ProviderRouter
        try:
            provider = self.router.select(capability)
            if provider and provider.provider_id:
                model_str = self._resolve_model_name(provider, capability)
                if model_str:
                    self._resolved_cache[capability] = model_str
                    return model_str
        except Exception as e:
            logger.debug("[ProviderManager] Router select failed for %s: %s", capability, e)

        # Second: fall back to ConfigurationService capability resolution
        try:
            model_str = config_service.resolve(capability)
            if model_str:
                self._resolved_cache[capability] = model_str
                return model_str
        except Exception as e:
            logger.debug("[ProviderManager] Config resolve failed for %s: %s", capability, e)

        # Final fallback: use the default local model
        from core.configuration.service import ConfigurationService
        model = ConfigurationService._local_model_for_capability(capability)
        model_str = f"ollama/{model}"
        self._resolved_cache[capability] = model_str
        return model_str

    def _resolve_model_name(self, provider: ExecutionProvider, capability: str) -> str | None:
        """Try to get a model name from a selected provider."""
        try:
            if hasattr(provider, 'default_model') and provider.default_model:
                prov_id = provider.provider_id or "ollama"
                return f"{prov_id}/{provider.default_model}"
        except Exception:
            pass
        return None

    def complete(self, capability: str, prompt: str, **kwargs) -> Any:
        """Route a completion through the best available provider for capability."""
        from core.llm_core import llm  # lazy import to avoid circular deps

        model = self.get_best_available(capability)
        kwargs.setdefault("model", model)
        return llm.complete(prompt, **kwargs)

    async def acomplete(self, capability: str, prompt: str, **kwargs) -> Any:
        """Async version of complete()."""
        from core.llm_core import llm

        model = self.get_best_available(capability)
        kwargs.setdefault("model", model)
        return await llm.acomplete(prompt, **kwargs)


provider_manager = ProviderManager()
