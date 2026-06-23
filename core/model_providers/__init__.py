"""core/model_providers/__init__.py
Unified ModelProvider architecture.
Re-exports all providers and the router.
"""
from core.model_providers.base import ModelProvider, ModelResult, ProviderStatus
from core.model_providers.ollama import OllamaProvider
from core.model_providers.openai import OpenAIProvider
from core.model_providers.anthropic import AnthropicProvider
from core.model_providers.gemini import GeminiProvider
from core.model_providers.groq import GroqProvider
from core.model_providers.openrouter import OpenRouterProvider
from core.model_providers.router import ModelRouter, TaskProfile, get_router
from core.model_providers.hybrid import HybridModelPlatform, HybridMode, ModelInfo, get_platform

__all__ = [
    "ModelProvider", "ModelResult", "ProviderStatus",
    "OllamaProvider", "OpenAIProvider", "AnthropicProvider",
    "GeminiProvider", "GroqProvider", "OpenRouterProvider",
    "ModelRouter", "TaskProfile", "get_router",
    "HybridModelPlatform", "HybridMode", "ModelInfo", "get_platform",
]
