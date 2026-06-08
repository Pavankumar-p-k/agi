
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

from litellm import Router

from core.errors import LLMError
from core.observability.metrics import observe_llm_latency
from core.result import Err, Ok, Result

logger = logging.getLogger(__name__)

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
        api_base = api_base or os.getenv("OLLAMA_URL", "http://localhost:11434")
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
    """Lazily build the model list from current env var values."""
    model_list = [
        {"model_name": "chat",      "litellm_params": _model_config("CHAT_MODEL",      "ollama/llama3.1:8b")},
        {"model_name": "code",      "litellm_params": _model_config("CODE_MODEL",      "ollama/qwen2.5-coder:3b")},
        {"model_name": "analysis",  "litellm_params": _model_config("ANALYSIS_MODEL",  "ollama/qwen2.5:7b")},
        {"model_name": "reasoning", "litellm_params": _model_config("REASONING_MODEL", "ollama/deepseek-r1:1.5b")},
        {"model_name": "vision",    "litellm_params": _model_config("VISION_MODEL",    "ollama/moondream:latest")},
        {"model_name": "grader",    "litellm_params": _model_config("GRADER_MODEL",    "ollama/phi3:mini")},
    ]

    if os.getenv("ANTHROPIC_API_KEY"):
        model_list.append({"model_name": "cloud", "litellm_params": {"model": "claude-sonnet-4-20250514", "api_key": os.getenv("ANTHROPIC_API_KEY")}})
    if os.getenv("OPENAI_API_KEY"):
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


async def complete(model_group: str, messages: list, timeout: int = 120) -> Result[str, LLMError]:
    from core.config_schema import jarvis_config
    if jarvis_config.failover.enabled:
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
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("http://localhost:11434/api/generate", json={
                "model": "moondream:latest", "prompt": prompt_text,
                "stream": False,
                "options": {"num_predict": 256, "temperature": 0.3, "num_gpu": 99}})
            if r.status_code == 200 and r.json().get("response", "").strip():
                return Ok(r.json()["response"].strip())
    except Exception as e:
        logger.debug("[Vision] Direct Ollama fallback failed: %s", e)

    for model_attempt in ["vision", "ollama/moondream"]:
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
    """Check if LLM is available (Ollama + model).
    Uses tinyllama for ping (fits 6GB VRAM), falls back to direct Ollama check."""
    import httpx
    async with httpx.AsyncClient(timeout=3) as client:
        try:
            r = await client.get("http://localhost:11434/api/tags")
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
            r = await client.post("http://localhost:11434/api/generate", json={
                "model": "tinyllama", "prompt": "ping", "stream": False,
                "options": {"num_predict": 10, "num_gpu": 99}})
            return r.status_code == 200 and bool(r.json().get("response", ""))
    except Exception as e:
        logger.warning("[LLM] Ollama tinyllama ping failed: %s", e)
        return False
