"""core/model_router.py
Central model registry + routing helpers for multi-Ollama setups.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List

from core.config import OLLAMA_URL


# Default per-model endpoints (Option 2: one Ollama server per model).
DEFAULT_MODEL_ENDPOINTS: Dict[str, str] = {
    "tinyllama": "http://127.0.0.1:11434",
    "deepseek-r1:1.5b": "http://127.0.0.1:11435",
    "qwen2.5-coder:3b": "http://127.0.0.1:11436",
    "qwen3:4b": "http://127.0.0.1:11437",
    "qwen2.5:7b": "http://127.0.0.1:11438",
    "mistral:7b": "http://127.0.0.1:11439",
    "llama3.1:8b": "http://127.0.0.1:11440",
    "phi3:mini": "http://127.0.0.1:11441",
    "moondream": "http://127.0.0.1:11442",
}


# Common aliases -> canonical model names.
MODEL_ALIASES: Dict[str, str] = {
    "llama3.1:latest": "llama3.1:8b",
    "llama3.1": "llama3.1:8b",
    "llama3": "llama3.1:8b",
    "tinyllama:latest": "tinyllama",
    "tinyllama:1.1b": "tinyllama",
    "moondream:latest": "moondream",
    "qwen3": "qwen3:4b",
    "qwen2.5": "qwen2.5:7b",
}


# Task roles -> model mapping (auto-switching by task).
ROLE_MODELS: Dict[str, str] = {
    "chat": "llama3.1:8b",
    "analysis": "qwen2.5:7b",
    "reasoning": "deepseek-r1:1.5b",
    "planning": "llama3.1:8b",
    "code": "qwen2.5-coder:3b",
    "automation": "qwen3:4b",
    "creative": "mistral:7b",
    "vision": "moondream",
    "classifier": "tinyllama",
    "emotion": "tinyllama",
    "quality": "phi3:mini",
    "fallback": "tinyllama",
}


# Fallback chain per model (on failure).
MODEL_FALLBACKS: Dict[str, List[str]] = {
    "llama3.1:8b": ["qwen2.5:7b", "mistral:7b", "qwen3:4b", "tinyllama"],
    "qwen2.5:7b": ["llama3.1:8b", "mistral:7b", "qwen3:4b", "tinyllama"],
    "mistral:7b": ["qwen2.5:7b", "llama3.1:8b", "qwen3:4b", "tinyllama"],
    "qwen3:4b": ["qwen2.5:7b", "llama3.1:8b", "mistral:7b", "tinyllama"],
    "qwen2.5-coder:3b": ["qwen2.5:7b", "llama3.1:8b", "qwen3:4b", "tinyllama"],
    "deepseek-r1:1.5b": ["qwen2.5:7b", "llama3.1:8b", "qwen3:4b", "tinyllama"],
    "phi3:mini": ["tinyllama"],
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


from core.privacy_classifier import privacy_classifier, PrivacyTier

def route_request(query: str, context: dict = None):
    """
    Route request based on privacy classifier.
    Returns (model_name, privacy_tier, processed_query).
    """
    tier = privacy_classifier.classify(query, context)
    processed_query = query
    
    if tier == PrivacyTier.LOCAL:
        # Strictly local
        model = model_for_role(route_role_for_text(query))
    elif tier == PrivacyTier.HYBRID:
        # Sanitize and then maybe cloud (if confidence is low, etc. - for now just local)
        processed_query = privacy_classifier.sanitize(query)
        model = model_for_role(route_role_for_text(processed_query))
    else:
        # Explicit cloud or complex
        model = "claude-3-5-sonnet-latest" # Example cloud model
    
    return model, tier, processed_query

