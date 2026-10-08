"""core.model_providers — model provider package (real, no stubs).

Re-exports the provider classes plus the router entry points:
    from core.model_providers import get_router, OllamaProvider, ModelRouter
"""
from __future__ import annotations

from core.model_providers.base import ModelProvider, ModelResult, ProviderState, ProviderStatus
from core.model_providers.ollama import OllamaProvider
from core.model_providers.openai import OpenAIProvider
from core.model_providers.anthropic import AnthropicProvider
from core.model_providers.gemini import GeminiProvider
from core.model_providers.groq import GroqProvider
from core.model_providers.openrouter import OpenRouterProvider
from core.model_providers.router import (
    DEFAULT_ROLE_MODELS,
    ModelRouter,
    TaskType,
    get_router,
    provider_for_role,
    reset_router,
)
from core.model_providers.hybrid import (
    HybridMode,
    HybridModelPlatform,
    ModelInfo,
    get_platform,
    reset_platform,
)

__all__ = [
    "ModelProvider",
    "ModelResult",
    "ProviderState",
    "ProviderStatus",
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "GroqProvider",
    "OpenRouterProvider",
    "ModelRouter",
    "TaskType",
    "DEFAULT_ROLE_MODELS",
    "get_router",
    "reset_router",
    "provider_for_role",
    "HybridMode",
    "HybridModelPlatform",
    "ModelInfo",
    "get_platform",
    "reset_platform",
]
