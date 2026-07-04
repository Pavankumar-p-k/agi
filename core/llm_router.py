# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""core/llm_router.py
LiteLLM Router — 6 model groups, all 126+ LiteLLM providers:
  chat/analysis/code/reasoning/vision/grader
Each group reads from .env (CHAT_MODEL, CODE_MODEL, etc.)
Default: local Ollama models, any LiteLLM provider with an API key.
"""

import logging
import os
import threading
import time

import httpx
from litellm import Router

from core.config_registry import config as _jarvis_config
from core.errors import LLMError
from core.observability.metrics import observe_llm_latency
from core.result import Err, Ok, Result

logger = logging.getLogger(__name__)

# ── Merged from core/model_router.py ─────────────────────────────────────

import re as _re

def _ollama_url() -> str:
    return os.getenv("OLLAMA_URL") or _jarvis_config.get("ollama.base_url")

DEFAULT_MODEL_ENDPOINTS: dict[str, str] = {
    "tinyllama": _ollama_url(),
    "deepseek-r1:1.5b": _ollama_url(),
    "qwen2.5-coder:3b": _ollama_url(),
    "qwen3:4b": _ollama_url(),
    "qwen2.5:7b": _ollama_url(),
    "mistral:7b": _ollama_url(),
    "llama3.1:8b": _ollama_url(),
    "phi3:mini": _ollama_url(),
    "moondream": _ollama_url(),
    "gemma4:e4b": _ollama_url(),
}

MODEL_ALIASES: dict[str, str] = {
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

ROLE_TO_GROUP: dict[str, str] = {
    "chat": "chat", "analysis": "analysis", "reasoning": "reasoning",
    "planning": "chat", "code": "code", "automation": "code",
    "build": "code", "creative": "chat", "vision": "vision",
    "classifier": "chat", "emotion": "chat", "quality": "grader",
    "deep": "nim-deep", "nim-code": "nim-code", "fallback": "chat",
}
ROLE_TO_ROUTER_GROUP = ROLE_TO_GROUP

ROLE_MODELS: dict[str, str] = {
    "chat": "llama3.1:8b", "analysis": "qwen2.5:7b",
    "reasoning": "deepseek-r1:1.5b", "planning": "qwen3:4b",
    "code": "qwen2.5:7b", "automation": "qwen2.5:7b",
    "creative": "mistral:7b", "vision": "moondream:latest",
    "classifier": "tinyllama", "emotion": "tinyllama",
    "quality": "phi3:mini", "deep": "qwen2.5:7b",
    "fallback": "tinyllama",
}

MODEL_FALLBACKS: dict[str, list[str]] = {
    "llama3.1:8b": ["qwen2.5:7b", "qwen2.5-coder:3b"],
    "qwen2.5:7b": ["llama3.1:8b", "qwen2.5-coder:3b"],
    "qwen2.5-coder:3b": ["qwen2.5:7b", "llama3.1:8b"],
    "gemma4:e4b": ["moondream", "llama3.1:8b"],
    "moondream": ["llama3.1:8b"],
    "mistral:7b": ["qwen2.5:7b", "llama3.1:8b"],
    "deepseek-r1:1.5b": ["qwen2.5:7b", "llama3.1:8b"],
    "tinyllama": [], "phi3:mini": ["tinyllama"], "qwen3:4b": ["tinyllama"],
}

_CACHED_ENDPOINTS: dict[str, str] | None = None

def resolve_model(name: str) -> str:
    key = (name or "").strip()
    if not key:
        return "chat"
    return MODEL_ALIASES.get(key, key)

def _parse_model_endpoints(raw: str) -> dict[str, str]:
    endpoints: dict[str, str] = {}
    for item in _re.split(r"[;\n,]+", raw or ""):
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

def _load_endpoints() -> dict[str, str]:
    raw = os.getenv("OLLAMA_MODEL_ENDPOINTS", "").strip()
    multi = os.getenv("OLLAMA_MULTI_INSTANCE", "").lower() in {"1", "true", "yes", "on"}
    if raw:
        return _parse_model_endpoints(raw)
    if multi:
        return DEFAULT_MODEL_ENDPOINTS.copy()
    return {}

def model_endpoints() -> dict[str, str]:
    global _CACHED_ENDPOINTS
    if _CACHED_ENDPOINTS is None:
        _CACHED_ENDPOINTS = _load_endpoints()
    return _CACHED_ENDPOINTS

def is_multi_instance() -> bool:
    return bool(model_endpoints())

def get_ollama_url(model: str | None = None) -> str:
    endpoints = model_endpoints()
    default_url = _ollama_url()
    if not endpoints or not model:
        return default_url
    model = resolve_model(model)
    return endpoints.get(model, default_url)

def group_for_role(role: str) -> str:
    return ROLE_TO_GROUP.get(role, "chat")

def model_for_role(role: str) -> str:
    model = os.getenv(f"{role.upper()}_MODEL", "")
    if not model:
        config_key = {
            "chat": "llm.chat_model", "code": "llm.code_model",
            "analysis": "llm.analysis_model", "reasoning": "llm.reasoning_model",
            "vision": "llm.vision_model", "embedding": "llm.embedding_model",
            "grader": "llm.grader_model",
        }.get(role)
        if config_key:
            model = _jarvis_config.get(config_key)
        if not model:
            model = ROLE_MODELS.get(role, "llama3.1:8b")
    if "/" in model:
        model = model.split("/", 1)[1]
    return model

get_router_model = group_for_role

def get_fallbacks(model: str) -> list[str]:
    model = resolve_model(model)
    return [resolve_model(m) for m in MODEL_FALLBACKS.get(model, [])]

# ── End merged from model_router.py ─────────────────────────────────────

def _model_config(env_var: str, default: str) -> dict:
    """
    Parse provider/model from env var. 
    Format: 'provider/model-id' or 'provider/model-id @api_base'
    Automatically injects API keys based on provider prefix.
    """
    raw = os.getenv(env_var, default)
    api_base = None

    if " @ " in raw:
        raw, api_base = raw.split(" @ ", 1)

    model = raw.strip()
    provider = model.split("/", 1)[0] if "/" in model else "openai"

    # Auto-map provider to API key env var
    # e.g. 'anthropic' -> 'ANTHROPIC_API_KEY'
    key_var = f"{provider.upper().replace('-', '_')}_API_KEY"
    api_key = os.getenv(key_var)

    # Special cases for Ollama / Local
    if provider == "ollama":
        api_base = api_base or os.getenv("OLLAMA_URL") or _jarvis_config.get("ollama.base_url")
        api_key = api_key or "not-needed"

    params = {
        "model": model,
        "api_key": api_key,
        "max_tokens": 4096,
        "temperature": 0.7
    }
    if api_base:
        params["api_base"] = api_base

    return params


_router_instance = None
_router_lock = threading.Lock()


def _build_model_list() -> list:
    """Lazily build the model list from current env var values (with config fallbacks)."""
    model_list = [
        {"model_name": "chat",      "litellm_params": _model_config("CHAT_MODEL",      _jarvis_config.get("llm.chat_model"))},
        {"model_name": "code",      "litellm_params": _model_config("CODE_MODEL",      _jarvis_config.get("llm.code_model"))},
        {"model_name": "analysis",  "litellm_params": _model_config("ANALYSIS_MODEL",  _jarvis_config.get("llm.analysis_model"))},
        {"model_name": "reasoning", "litellm_params": _model_config("REASONING_MODEL", _jarvis_config.get("llm.reasoning_model"))},
        {"model_name": "vision",    "litellm_params": _model_config("VISION_MODEL",    _jarvis_config.get("llm.vision_model"))},
        {"model_name": "grader",    "litellm_params": _model_config("GRADER_MODEL",    _jarvis_config.get("llm.grader_model"))},
        {"model_name": "embedding",   "litellm_params": _model_config("EMBEDDING_MODEL",   _jarvis_config.get("llm.embedding_model"))},
        {"model_name": "orchestrator","litellm_params": _model_config("ORCHESTRATOR_MODEL", _jarvis_config.get("llm.orchestrator_model"))},
        {"model_name": "fallback",    "litellm_params": _model_config("FALLBACK_MODEL",    _jarvis_config.get("llm.fallback_model"))},
    ]

    if _jarvis_config.get("llm.cloud_model"):
        model_list.append({"model_name": "cloud", "litellm_params": {"model": _jarvis_config.get("llm.cloud_model")}})
    elif os.getenv("ANTHROPIC_API_KEY"):
        model_list.append({"model_name": "cloud", "litellm_params": {"model": "claude-sonnet-4-20250514", "api_key": os.getenv("ANTHROPIC_API_KEY")}})
    elif os.getenv("OPENAI_API_KEY"):
        model_list.append({"model_name": "cloud", "litellm_params": {"model": "gpt-4o", "api_key": os.getenv("OPENAI_API_KEY")}})

    return model_list


def get_router():
    global _router_instance
    if _router_instance is None:
        with _router_lock:
            if _router_instance is None:
                os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")
                os.environ.setdefault("LITELLM_LOG", "WARNING")
                _router_instance = Router(model_list=_build_model_list())
    return _router_instance


def refresh_router():
    """Rebuild the router with fresh env values. Call after changing env vars at runtime."""
    global _router_instance
    with _router_lock:
        _router_instance = None
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")
        os.environ.setdefault("LITELLM_LOG", "WARNING")
        _router_instance = Router(model_list=_build_model_list())
    return _router_instance


def get_available_providers() -> list[dict]:
    """Return list of all 126+ providers supported by LiteLLM and their status."""
    from litellm import provider_list
    return [
        {"name": p, "configured": bool(os.getenv(f"{p.upper().replace('-', '_')}_API_KEY"))}
        for p in provider_list
    ]


def _ollama_reachable() -> bool:
    """Ping the configured Ollama host. Returns True if reachable in under 2s."""
    _ollama = _jarvis_config.get("ollama.base_url")
    try:
        r = httpx.get(f"{_ollama}/api/tags", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


async def complete(model_group: str, messages: list, timeout: int = 120) -> Result[str, LLMError]:
    from core.config_schema import jarvis_config

    # If Ollama is reachable locally, skip failover entirely
    if jarvis_config.failover.enabled and _ollama_reachable():
        pass  # skip failover — local model is available
    elif jarvis_config.failover.enabled:
        from core.llm_failover import llm_failover
        return await llm_failover.complete(model_group, messages, timeout=timeout)

    try:
        from core.plugins import plugin_registry
        resolved = model_group
        for _, result in await plugin_registry.run_hook("before_model_resolve", model_role=model_group, task=""):
            if isinstance(result, str) and result:
                resolved = result

        for _, result in await plugin_registry.run_hook("llm_input", messages=messages):
            if isinstance(result, list):
                messages = result

        await plugin_registry.run_hook("model_call_started", model=resolved, messages=messages)

        start = time.time()
        response = await get_router().acompletion(
            model=resolved,
            messages=messages,
            timeout=timeout,
        )
        elapsed = time.time() - start
        observe_llm_latency(elapsed)
        content = response.choices[0].message.content

        for _, result in await plugin_registry.run_hook("llm_output", response=content):
            if isinstance(result, str):
                content = result

        await plugin_registry.run_hook("model_call_ended", model=resolved, response=content, duration=elapsed)

        return Ok(content)
    except Exception as e:
        logger.warning("[LLM] complete(%s) failed: %s", model_group, e)
        return Err(LLMError(str(e)))


_VISION_KEYWORDS = frozenset([
    "screen", "screenshot", "what do you see", "look at this",
    "what is this", "what's this", "describe this image",
    "describe the image", "what error", "what's on my screen",
    "what is on my screen", "what am i looking at",
])


def _has_vision_content(messages: list) -> bool:
    text_lower = ""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "image_url":
                        return True
                    text_lower += str(part.get("text", "")).lower()
        elif isinstance(content, str):
            text_lower += content.lower()
    for kw in _VISION_KEYWORDS:
        if kw in text_lower:
            return True
    return False


async def complete_vision(messages: list, timeout: int = 120) -> Result[str, LLMError]:
    """Vision-aware completion: gemma4:e4b â†’ moondream â†’ chat.
    If messages already contain [SCREEN CAPTURE: ...], skip vision model and use chat.
    Returns Ok(str) on success or Err(LLMError) on failure."""
    if not _has_vision_content(messages):
        return await complete("chat", messages, timeout)

    last = messages[-1]["content"] if messages else ""
    if isinstance(last, str) and "[SCREEN CAPTURE:" in last:
        return await complete("chat", messages, timeout)

    import httpx
    prompt_text = last if isinstance(last, str) else ""
    _ollama = _jarvis_config.get("ollama.base_url")
    _vision_model = _jarvis_config.get("llm.vision_model")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{_ollama}/api/generate", json={
                "model": _vision_model, "prompt": prompt_text,
                "stream": False,
                "options": {"num_predict": 256, "temperature": 0.3, "num_gpu": 99}})
            if r.status_code == 200 and r.json().get("response", "").strip():
                return Ok(r.json()["response"].strip())
    except Exception as e:
        logger.debug("[Vision] Direct Ollama fallback failed: %s", e)

    for model_attempt in ["vision", _vision_model]:
        try:
            resp = await get_router().acompletion(
                model=model_attempt, messages=messages, timeout=15)
            return Ok(resp.choices[0].message.content)
        except Exception as e:
            logger.debug("[Vision] LiteLLM %s failed: %s", model_attempt, e)
            continue

    fallback = await complete("chat", messages, timeout)
    if fallback.is_err():
        logger.warning("[Vision] All vision fallbacks exhausted: %s", fallback._error)
    return fallback


async def health_check() -> bool:
    """Check if LLM is available (Ollama + model)."""
    import httpx
    _ollama = _jarvis_config.get("ollama.base_url")
    _ping_model = _jarvis_config.get("llm.ping_model")
    async with httpx.AsyncClient(timeout=3) as client:
        try:
            r = await client.get(f"{_ollama}/api/tags")
            if r.status_code != 200:
                logger.warning("[LLM] Ollama /api/tags returned %s", r.status_code)
                return False
        except Exception as e:
            logger.warning("[LLM] Ollama /api/tags check failed: %s", e)
            return False
    # Try LiteLLM Router with smallest model first
    try:
        await get_router().acompletion(
            model="chat",
            messages=[{"role": "user", "content": "ping"}],
            timeout=10,
        )
        return True
    except Exception as e:
        logger.debug("[LLM] LiteLLM ping failed: %s", e)
    # Fallback: direct Ollama completion on tinyllama
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{_ollama}/api/generate", json={
                "model": _ping_model, "prompt": "ping", "stream": False,
                "options": {"num_predict": 10, "num_gpu": 99}})
            return r.status_code == 200 and bool(r.json().get("response", ""))
    except Exception as e:
        logger.warning("[LLM] Ollama ping failed: %s", e)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# NEW: Config-driven model name resolver (added by config migration)
# Import: from core.llm_router import get_model_for_group, get_config_router
# ══════════════════════════════════════════════════════════════════════════════

from typing import Optional as _Optional

GROUP_CONFIG_KEYS = {
    "chat":         "llm.chat_model",
    "code":         "llm.code_model",
    "analysis":     "llm.analysis_model",
    "reasoning":    "llm.reasoning_model",
    "vision":       "llm.vision_model",
    "embedding":    "llm.embedding_model",
    "grader":       "llm.grader_model",
    "orchestrator": "llm.orchestrator_model",
    "fallback":     "llm.fallback_model",
}


def get_model_for_group(group: str, fallback: _Optional[str] = None) -> str:
    """Return configured model name for the given group from config."""
    from core.config_registry import config

    config_key = GROUP_CONFIG_KEYS.get(group)
    if not config_key:
        logger.warning(f"Unknown model group: '{group}', using fallback")
        return fallback or config.get("llm.fallback_model")

    model = config.get(config_key)
    if not model:
        logger.warning(f"Model for group '{group}' is empty, using fallback")
        return fallback or config.get("llm.fallback_model")

    return model


class LLMRouter:
    """Central model-name router — reads all names from config registry."""

    def get(self, group: str) -> str:
        return get_model_for_group(group)

    def get_for_role(self, role: str) -> str:
        from core.config_registry import config
        role_key = f"role_models.{role}"
        try:
            model = config.get(role_key)
            if model:
                return model
        except KeyError:
            pass
        return config.get("role_models.default") or config.get("llm.fallback_model")

    def get_ollama_base_url(self) -> str:
        from core.config_registry import config
        return config.get("ollama.base_url")

    def get_all_models(self) -> dict:
        from core.config_registry import config
        return {group: config.get(key) for group, key in GROUP_CONFIG_KEYS.items()}


_config_router = LLMRouter()


def get_config_router() -> LLMRouter:
    """Return the config-driven LLMRouter singleton (new API)."""
    return _config_router
