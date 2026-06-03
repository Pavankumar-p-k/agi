
"""core/model_router.py
Central model registry + routing helpers.
Single source of truth for roleâ†’group mapping.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List

from core.config import OLLAMA_URL
from core.privacy_classifier import privacy_classifier, PrivacyTier


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


MODEL_ALIASES: Dict[str, str] = {
    "llama3.1:latest": "llama3.1:8b",
    "llama3.1": "llama3.1:8b",
    "llama3": "llama3.1:8b",
    "tinyllama:latest": "tinyllama",
    "tinyllama:1.1b": "tinyllama",
    "moondream": "moondream:latest",
    "moondream:latest": "moondream:latest",
    "gemma4": "gemma4:e4b",
    "gemma4:latest": "gemma4:e4b",
    "qwen3": "qwen3:4b",
    "qwen2.5": "qwen2.5:7b",
}


# Role â†’ llm_router model group mapping (single source of truth).
ROLE_TO_GROUP: Dict[str, str] = {
    "chat": "chat",
    "analysis": "analysis",
    "reasoning": "reasoning",
    "planning": "chat",
    "code": "code",
    "automation": "code",
    "build": "code",
    "creative": "chat",
    "vision": "vision",
    "classifier": "chat",
    "emotion": "chat",
    "quality": "grader",
    "deep": "nim-deep",
    "nim-code": "nim-code",
    "fallback": "chat",
}

# Backward-compatible alias for existing imports.
ROLE_TO_ROUTER_GROUP = ROLE_TO_GROUP

# Role â†’ actual Ollama model name (for direct API callers, not llm_router).
ROLE_MODELS: Dict[str, str] = {
    "chat": "llama3.1:8b",
    "analysis": "qwen2.5:7b",
    "reasoning": "deepseek-r1:1.5b",
    "planning": "qwen3:4b",
    "code": "qwen2.5-coder:3b",
    "automation": "qwen2.5-coder:3b",
    "creative": "mistral:7b",
    "vision": "moondream:latest",
    "classifier": "tinyllama",
    "emotion": "tinyllama",
    "quality": "phi3:mini",
    "deep": "qwen2.5:7b",
    "fallback": "tinyllama",
}


_CACHED_ENDPOINTS: Dict[str, str] | None = None


def resolve_model(name: str) -> str:
    key = (name or "").strip()
    if not key:
        return "chat"
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


def group_for_role(role: str) -> str:
    """Return the llm_router group name for a role."""
    return ROLE_TO_GROUP.get(role, "chat")


def model_for_role(role: str) -> str:
    """Return the actual model name for a role (for direct Ollama API calls)."""
    model = os.getenv(f"{role.upper()}_MODEL", "")
    if not model:
        model = ROLE_MODELS.get(role, "llama3.1:8b")
    
    # Strip provider prefix if present for direct Ollama calls
    # e.g. 'ollama/llama3.1:8b' -> 'llama3.1:8b'
    if "/" in model:
        model = model.split("/", 1)[1]
    return model


get_router_model = group_for_role  # backward-compatible alias

# Fallback chain per model (for GPU pool / legacy callers).
MODEL_FALLBACKS: Dict[str, List[str]] = {
    "llama3.1:8b": ["qwen2.5:7b", "qwen2.5-coder:3b"],
    "qwen2.5:7b": ["llama3.1:8b", "qwen2.5-coder:3b"],
    "qwen2.5-coder:3b": ["qwen2.5:7b", "llama3.1:8b"],
    "gemma4:e4b": ["moondream", "llama3.1:8b"],
    "moondream": ["llama3.1:8b"],
    "mistral:7b": ["qwen2.5:7b", "llama3.1:8b"],
    "deepseek-r1:1.5b": ["qwen2.5:7b", "llama3.1:8b"],
    "tinyllama": [],
    "phi3:mini": ["tinyllama"],
    "qwen3:4b": ["tinyllama"],
}

def get_fallbacks(model: str) -> List[str]:
    model = resolve_model(model)
    return [resolve_model(m) for m in MODEL_FALLBACKS.get(model, [])]


def route_role_for_text(text: str) -> str:
    """Lightweight heuristic router for text-only tasks."""
    t = (text or "").lower()
    if any(k in t for k in ("deep research", "thorough analysis", "comprehensive", "deep dive", "expert analysis", "in-depth")):
        return "deep"
    if any(k in t for k in ("code", "bug", "stack trace", "exception", "compile", "syntax")):
        return "code"
    if any(k in t for k in ("analyze", "analysis", "compare", "pros and cons", "decision")):
        return "analysis"
    if any(k in t for k in ("write", "rewrite", "story", "poem", "script", "lyrics", "email")):
        return "creative"
    if any(k in t for k in ("plan", "steps", "schedule", "roadmap", "automate", "workflow")):
        return "reasoning"
    return "chat"


# Health monitor callback â€” set during startup by core/main.py
_health_checker: callable = lambda: True

def set_health_checker(fn: callable):
    """Inject health-monitor callback (set during server startup)."""
    global _health_checker
    _health_checker = fn


def route_request(query: str, context: dict = None, force_tier: str = None):
    """
    Route request based on privacy classifier.
    Auto-fails over to cloud if Ollama is down and cloud keys are available.
    
    Returns (router_group, privacy_tier, processed_query).
    """
    if force_tier == "cloud":
        return "cloud", PrivacyTier.CLOUD, query
    if force_tier == "local":
        tier = privacy_classifier.classify(query, context)
        processed_query = query
        if tier == PrivacyTier.HYBRID:
            processed_query = privacy_classifier.sanitize(query, tier=PrivacyTier.HYBRID)
        role = route_role_for_text(processed_query)
        return group_for_role(role), PrivacyTier.LOCAL, processed_query

    if os.getenv("FORCE_CLOUD", "").lower() in ("1", "true", "yes"):
        return "cloud", PrivacyTier.CLOUD, query

    # Auto-failover to cloud if Ollama is down
    if not _health_checker():
        if os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY"):
            return "cloud", PrivacyTier.CLOUD, query

    tier = privacy_classifier.classify(query, context)
    processed_query = query

    if tier == PrivacyTier.HYBRID:
        processed_query = privacy_classifier.sanitize(query, tier=PrivacyTier.HYBRID)

    role = route_role_for_text(processed_query)
    return group_for_role(role), tier, processed_query
