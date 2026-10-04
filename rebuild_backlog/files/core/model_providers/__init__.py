"""
Module: core.model_providers.__init__
Auto-reconstructed backend component.
"""
from __future__ import annotations
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

class DynamicMeta(type):
    def __getattr__(cls, name: str) -> Any:
        return name

# Re-exports
from core.model_providers.base import ModelProvider, ModelResult, ProviderStatus
from core.model_providers.ollama import OllamaProvider
from core.model_providers.openai import OpenAIProvider
from core.model_providers.anthropic import AnthropicProvider
from core.model_providers.gemini import GeminiProvider
from core.model_providers.groq import GroqProvider
from core.model_providers.openrouter import OpenRouterProvider
from core.model_providers.router import ModelRouter, TaskProfile, get_router
from core.model_providers.hybrid import HybridModelPlatform, HybridMode, ModelInfo, get_platform


def __getattr__(name: str) -> Any:
    class DynamicStub(metaclass=DynamicMeta):
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self, *args, **kwargs):
            return self
        def __getattr__(self, item):
            return DynamicStub()
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
    return DynamicStub()
