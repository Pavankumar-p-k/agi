"""core/model_router.py
Central model registry + routing helpers for multi-Ollama setups.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List

from core.config import OLLAMA_URL
from core.privacy_classifier import privacy_classifier, PrivacyTier


# Default per-model endpoints (Option 2: one Ollama server per model).
DEFAULT_MODEL_ENDPOINTS: Dict[str, str] = {
    "tinyllama": "http://localhost:11434",
    "deepseek-r1:1.5b": "http://localhost:11434",
    "qwen2.5-coder:3b": "http://localhost:11434",
    "qwen3:4b": "http://localhost:11434",
    "qwen2.5:7b": "http://localhost:11434",
    "mistral:7b": "http://localhost:11434",
    "llama3.1:8b": "http://localhost:11434",
    "phi3:mini": "http://localhost:11434",
    "moondream": "http://localhost:11434",
    "gemma4:e4b": "http://localhost:11434",
}


# Common aliases -> canonical model names.
MODEL_ALIASES: Dict[str, str] = {
    "llama3.1:latest": "llama3.1:8b",
    "llama3.1": "llama3.1:8b",
    "llama3": "llama3.1:8b",
    "tinyllama:latest": "tinyllama",
    "tinyllama:1.1b": "tinyllama",
    "moondream:latest": "moondream",
    "gemma4": "gemma4:e4b",
    "gemma4:latest": "gemma4:e4b",
    "qwen3": "qwen3:4b",
    "qwen2.5": "qwen2.5:7b",
}


# Task roles -> model mapping (auto-switching by task).
ROLE_MODELS: Dict[str, str] = {
    "chat": "gemma4:e4b",
    "analysis": "qwen2.5:7b",
    "reasoning": "deepseek-r1:1.5b",
    "planning": "qwen3:4b",
    "code": "qwen2.5-coder:3b",
    "automation": "qwen3:4b",
    "creative": "mistral:7b",
    "vision": "gemma4:e4b",
    "classifier": "tinyllama",
    "emotion": "tinyllama",
    "quality": "phi3:mini",
    "fallback": "tinyllama",
}


# Fallback chain per model (on failure).
MODEL_FALLBACKS: Dict[str, List[str]] = {
    "qwen3:4b": ["tinyllama", "phi3:mini"],
    "llama3.1:8b": ["qwen2.5:7b", "mistral:7b", "qwen3:4b", "tinyllama"],
    "qwen2.5:7b": ["llama3.1:8b", "mistral:7b", "qwen3:4b", "tinyllama"],
    "mistral:7b": ["qwen2.5:7b", "llama3.1:8b", "qwen3:4b", "tinyllama"],
    "qwen2.5-coder:3b": ["qwen2.5:7b", "llama3.1:8b", "qwen3:4b", "tinyllama"],
    "deepseek-r1:1.5b": ["qwen2.5:7b", "llama3.1:8b", "qwen3:4b", "tinyllama"],
    "phi3:mini": ["tinyllama"],
    "gemma4:e4b": ["moondream", "llama3.1:8b", "qwen2.5:7b"],
    "moondream": ["llama3.1:8b", "qwen2.5:7b"],
    "tinyllama": [],
}


_CACHED_ENDPOINTS: Dict[str, str] | None = None


def resolve_model(name: str) -> str:
    key = (name or "").strip()
    if not key:
        return ROLE_MODELS["chat"]
    return MODEL_ALIASES.get(key, key)


def _parse_model_endpoints(raw: str) -> Dict[str, str]:
    endpoints: Dict[str, str] = {}
    for item in re.split(r"[;\n,]+", raw or ""):
        item = item.strip()
        if not item or "=" not in item:
            continue
        model, url = item.split("=", 1)
        model = resolve_model(model.strip())
        url = url.strip()
        if url and not url.startswith("http"):
            url = "http://" + url
        if model and url:
            endpoints[model] = url
    return endpoints


def _load_endpoints() -> Dict[str, str]:
    raw = os.getenv("OLLAMA_MODEL_ENDPOINTS", "").strip()
    multi = os.getenv("OLLAMA_MULTI_INSTANCE", "").lower() in {"1", "true", "yes", "on"}
    if raw:
        return _parse_model_endpoints(raw)
    if multi:
        return DEFAULT_MODEL_ENDPOINTS.copy()
    return {}


def model_endpoints() -> Dict[str, str]:
    global _CACHED_ENDPOINTS
    if _CACHED_ENDPOINTS is None:
        _CACHED_ENDPOINTS = _load_endpoints()
    return _CACHED_ENDPOINTS


def is_multi_instance() -> bool:
    return bool(model_endpoints())


def get_ollama_url(model: str | None = None) -> str:
    endpoints = model_endpoints()
    if not endpoints or not model:
        return OLLAMA_URL
    model = resolve_model(model)
    return endpoints.get(model, OLLAMA_URL)


def model_for_role(role: str) -> str:
    return resolve_model(ROLE_MODELS.get(role, ROLE_MODELS["chat"]))


def get_fallbacks(model: str) -> List[str]:
    model = resolve_model(model)
    return [resolve_model(m) for m in MODEL_FALLBACKS.get(model, [])]


def route_role_for_text(text: str) -> str:
    """Lightweight heuristic router for text-only tasks."""
    t = (text or "").lower()
    if any(k in t for k in ("code", "bug", "stack trace", "exception", "compile", "syntax")):
        return "code"
    if any(k in t for k in ("plan", "steps", "schedule", "roadmap", "automate", "workflow")):
        return "reasoning"
    if any(k in t for k in ("analyze", "analysis", "compare", "pros and cons", "decision")):
        return "analysis"
    if any(k in t for k in ("write", "rewrite", "story", "poem", "script", "lyrics", "email")):
        return "creative"
    return "chat"


def route_request(query: str, context: dict = None, force_tier: str = None):
    """
    Route request based on privacy classifier.
    
    Args:
        query: The user's message
        context: Optional context dict
        force_tier: "cloud" to force cloud API, "local" to force local, None for auto
    
    Returns (model_name, privacy_tier, processed_query).
    """
    # Explicit user choice overrides everything
    if force_tier == "cloud":
        return "cloud", PrivacyTier.CLOUD, query
    if force_tier == "local":
        tier = privacy_classifier.classify(query, context)
        processed_query = query
        if tier == PrivacyTier.LOCAL:
            model = model_for_role(route_role_for_text(query))
        elif tier == PrivacyTier.HYBRID:
            processed_query = privacy_classifier.sanitize(query, tier=PrivacyTier.HYBRID)
            model = model_for_role(route_role_for_text(processed_query))
        else:
            model = model_for_role(route_role_for_text(query))
        return model, PrivacyTier.LOCAL, processed_query

    # FORCE_CLOUD env var as default when no user choice
    if os.getenv("FORCE_CLOUD", "").lower() in ("1", "true", "yes"):
        return "cloud", PrivacyTier.CLOUD, query

    tier = privacy_classifier.classify(query, context)
    processed_query = query
    
    if tier == PrivacyTier.LOCAL:
        model = model_for_role(route_role_for_text(query))
    elif tier == PrivacyTier.HYBRID:
        processed_query = privacy_classifier.sanitize(query, tier=PrivacyTier.HYBRID)
        model = model_for_role(route_role_for_text(processed_query))
    else:
        model = model_for_role(route_role_for_text(query))
    
    return model, tier, processed_query


ROLE_TO_ROUTER_GROUP: Dict[str, str] = {
    "chat": "chat",
    "analysis": "analysis",
    "reasoning": "reasoning",
    "planning": "chat",
    "code": "code",
    "automation": "automation",
    "build": "automation",
    "creative": "creative",
    "vision": "vision",
    "classifier": "fast",
    "emotion": "fast",
    "quality": "fast",
    "fallback": "fast",
}


def get_router_model(role: str) -> str:
    return ROLE_TO_ROUTER_GROUP.get(role, "chat")

