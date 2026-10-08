"""core.model_providers.router — role-based model router with health check.

Rebuilt from the committed contracts:

- jarvis-export/cli/cli_commands.py (doctor):
      from core.model_providers import get_router
      health = asyncio.run(router.health_check())
      -> {provider_name: status} with .available / .healthy / .latency_ms
- jarvis-export/cli/cli_commands.py (jarvis models assign):
      from core.model_providers.router import TaskType, DEFAULT_ROLE_MODELS
      for t in TaskType: DEFAULT_ROLE_MODELS[t.value]
- tests/architecture/test_phase5_hybrid_router.py:
      health_check() returns dict; values expose .available/.healthy/.latency_ms
      (sync objects, NOT coroutine/NULL); local when OLLAMA_URL even offline.
"""
from __future__ import annotations

import asyncio
import os
from enum import Enum
from typing import Any, Optional

from core.model_providers.base import ProviderStatus
from core.model_providers.ollama import OllamaProvider

# --------------------------------------------------------------------------- #
# Roles                                                                       #
# --------------------------------------------------------------------------- #
class TaskType(str, Enum):
    """Model roles JARVIS assigns models to."""

    CHAT = "chat"
    CODE = "code"
    VISION = "vision"
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    EMBEDDING = "embedding"
    ORCHESTRATOR = "orchestrator"


ROLE_MODEL_ENV: dict[str, str] = {
    TaskType.CHAT: "CHAT_MODEL",
    TaskType.CODE: "CODE_MODEL",
    TaskType.VISION: "VISION_MODEL",
    TaskType.REASONING: "REASONING_MODEL",
    TaskType.ANALYSIS: "ANALYSIS_MODEL",
    TaskType.EMBEDDING: "EMBEDDING_MODEL",
    TaskType.ORCHESTRATOR: "ORCHESTRATOR_MODEL",
}

DEFAULT_ROLE_MODELS: dict[str, str] = {
    "chat": os.getenv("CHAT_MODEL", "ollama/qwen2.5-coder:3b"),
    "code": os.getenv("CODE_MODEL", "ollama/qwen2.5-coder:3b"),
    "vision": os.getenv("VISION_MODEL", "ollama/llava:7b"),
    "reasoning": os.getenv("REASONING_MODEL", "ollama/qwen2.5-coder:3b"),
    "analysis": os.getenv("ANALYSIS_MODEL", "ollama/qwen2.5-coder:3b"),
    "embedding": os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
    "orchestrator": os.getenv("ORCHESTRATOR_MODEL", "ollama/qwen2.5-coder:3b"),
}


def _parse_model_ref(ref: str) -> tuple[str, str]:
    """Split "provider/model-id" -> ("provider", "model-id"). "x" -> ("", "x")."""
    if "/" in ref:
        provider, _, model_id = ref.partition("/")
        return provider.strip(), model_id
    return "", ref


def _build(provider_id: str, model_id: str):
    """Instantiate a concrete provider for a parsed role model ref."""
    provider_id = (provider_id or "").lower()
    if provider_id in ("", "ollama", "local"):
        return OllamaProvider(model=model_id)
    from core.model_providers.openai import OpenAIProvider
    from core.model_providers.anthropic import AnthropicProvider
    from core.model_providers.gemini import GeminiProvider
    from core.model_providers.groq import GroqProvider
    from core.model_providers.openrouter import OpenRouterProvider

    mapping = {
        "openai": OpenAIProvider,
        "gpt": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "claude": AnthropicProvider,
        "gemini": GeminiProvider,
        "groq": GroqProvider,
        "openrouter": OpenRouterProvider,
    }
    cls = mapping.get(provider_id)
    if cls is None:
        raise LookupError(f"unknown model provider: {provider_id!r}")
    return cls(model=model_id)


def provider_for_role(role: str) -> Any:
    """Build the provider instance configured for a role.

    Accepts role names ("chat") or full refs ("ollama/qwen2.5:3b"). Falls back
    to the chat role when the role is unknown.
    """
    role_key = (role or "chat").lower()
    if role_key not in DEFAULT_ROLE_MODELS:
        role_key = "chat"
    return _build(*_parse_model_ref(DEFAULT_ROLE_MODELS.get(role_key, "")))


# --------------------------------------------------------------------------- #
# Router                                                                      #
# --------------------------------------------------------------------------- #
class ModelRouter:
    """Health + role routing over the configured model providers."""

    def __init__(self, ollama_provider: Optional[OllamaProvider] = None,
                 cloud_providers: Optional[list] = None) -> None:
        self._ollama = ollama_provider
        self._cloud = cloud_providers

    def _providers(self) -> list:
        """All providers that can appear in the health table.

        Ollama is ALWAYS listed (the doctor contract pins: local provider is
        reported even when the daemon is offline). Cloud providers appear
        only when their API key is set.
        """
        if self._ollama is not None or self._cloud is not None:
            out: list = []
            if self._ollama is not None:
                out.append(self._ollama)
            out.extend(self._cloud or [])
            return out

        from core.model_providers.openai import OpenAIProvider
        from core.model_providers.anthropic import AnthropicProvider

        providers: list = [self._get_ollama()]
        if OpenAIProvider.api_key():
            providers.append(OpenAIProvider())
        if AnthropicProvider.api_key():
            providers.append(AnthropicProvider())
        return providers

    def _get_ollama(self) -> OllamaProvider:
        if self._ollama is None:
            self._ollama = OllamaProvider()
        return self._ollama

    async def health_check(self) -> dict[str, Any]:
        """Health snapshot per provider, keyed by provider id.

        Contract: doctor calls ``asyncio.run(router.health_check())``, so the
        method MUST be a coroutine; values are sync ProviderStatus objects
        exposing .available / .healthy / .latency_ms.
        """
        health: dict[str, Any] = {}
        for provider in self._providers():
            try:
                status = provider.health()
                if asyncio.iscoroutine(status):
                    status = await status
            except Exception as exc:  # noqa: BLE001 - a broken provider must not
                # kill the whole health table
                pid = getattr(provider, "provider_id", "?")
                status = ProviderStatus(provider=pid, error=str(exc))
            if not isinstance(status, ProviderStatus):
                status = ProviderStatus(provider=getattr(provider, "provider_id", "?"))
            health[provider.provider_id] = status
        return health

    def select(self, role: str, **kwargs: Any):
        """Provider instance to serve a role/model request.

        Accepts a role name or a full "provider/model" ref.
        """
        return provider_for_role(role)

    def complete(self, prompt: str, role: str = "chat", **kwargs: Any) -> Any:
        provider = provider_for_role(role)
        return provider.complete(prompt, **kwargs)


_router_instance: Optional[ModelRouter] = None
_router_lock = asyncio.Lock()


def get_router(*, reset: bool = False) -> ModelRouter:
    """Singleton router (doctor + CLI surface)."""
    global _router_instance
    if reset:
        _router_instance = None
        return _router_instance  # type: ignore[return-value]
    if _router_instance is None:
        _router_instance = ModelRouter()
    return _router_instance


def reset_router() -> None:
    """Drop the cached router (test seam / env change)."""
    global _router_instance
    _router_instance = None


__all__ = [
    "TaskType",
    "DEFAULT_ROLE_MODELS",
    "ModelRouter",
    "get_router",
    "reset_router",
    "provider_for_role",
    "_parse_model_ref",
    "_build",
]
