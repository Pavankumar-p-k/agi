"""LLM router — single entry point for all model calls.

Routes requests to Ollama (local, default) or cloud providers configured
via environment (OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY,
GROQ_API_KEY, OPENROUTER_API_KEY). Built on top of jarvis_provider.py,
which owns the provider implementations.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from types import SimpleNamespace
from typing import Any, List, Optional

from core.result import Err, Ok, Result

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Role -> model reference ("provider/model-id"). Cloud roles require the
# matching API key; a missing key falls back to Ollama with a warning.
ROLE_MODELS: dict[str, str] = {
    "chat": os.getenv("CHAT_MODEL", "ollama/qwen2.5-coder:3b"),
    "code": os.getenv("CODE_MODEL", "ollama/qwen2.5-coder:3b"),
    "vision": os.getenv("VISION_MODEL", "ollama/llava:7b"),
    "reasoning": os.getenv("REASONING_MODEL", "ollama/qwen2.5-coder:3b"),
    "analysis": os.getenv("ANALYSIS_MODEL", "ollama/qwen2.5-coder:3b"),
    "embedding": os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
}

# Friendly/legacy names -> canonical roles.
MODEL_ALIASES: dict[str, str] = {
    "default": "chat",
    "automation": "chat",
    "chat": "chat",
    "code": "code",
    "coder": "code",
    "codegen": "code",
    "vision": "vision",
    "image": "vision",
    "reasoning": "reasoning",
    "think": "reasoning",
    "plan": "reasoning",
    "quality": "reasoning",
    "analysis": "analysis",
}

MODEL_FALLBACKS: dict[str, str] = {
    "vision": "chat",
    "reasoning": "chat",
    "analysis": "chat",
    "code": "chat",
}


def get_ollama_url() -> str:
    """Base URL of the local Ollama daemon."""
    return OLLAMA_URL


def model_for_role(role: str) -> str:
    """Model reference configured for a role (falls back to chat)."""
    role = MODEL_ALIASES.get(role, role)
    return ROLE_MODELS.get(role, ROLE_MODELS["chat"])


def get_available_providers() -> List[dict]:
    """Providers that can currently serve requests (Ollama + clouds with keys)."""
    providers: List[dict] = [{"id": "ollama", "enabled": True, "local": True,
                              "url": OLLAMA_URL}]
    cloud_keys = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    for pid, key_env in cloud_keys.items():
        providers.append({
            "id": pid,
            "enabled": bool(os.getenv(key_env)),
            "local": False,
        })
    return providers


def _provider_for(model: str | None, role: str):
    """Resolve a model reference / role to a configured LLMProvider."""
    import jarvis_provider as jp

    if model:
        provider_id, model_id = jp._parse_model_ref(model)
        return jp._build(provider_id, model_id)
    return jp.get_provider(role)


def _build_prompt(prompt: str, system: Optional[str]) -> str:
    if system:
        return f"{system}\n\n{prompt}"
    return prompt


def complete(
    prompt: str,
    *,
    model: Optional[str] = None,
    role: str = "chat",
    system: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: Optional[int] = None,
    **kwargs: Any,
) -> Result[str]:
    """Synchronous single-turn completion. Returns Ok(text) or Err(error)."""
    try:
        provider = _provider_for(model, role)
        text = provider.chat(
            _build_prompt(prompt, system),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return Ok(str(text))
    except Exception as exc:  # noqa: BLE001 — callers handle Err
        logger.warning("llm_router.complete failed: %s", exc)
        return Err(exc)


async def complete_async(
    prompt: str,
    *,
    model: Optional[str] = None,
    role: str = "chat",
    system: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: Optional[int] = None,
    **kwargs: Any,
) -> Result[str]:
    """Async variant of complete() — runs the blocking call in a thread."""
    return await asyncio.to_thread(
        complete, prompt, model=model, role=role, system=system,
        temperature=temperature, max_tokens=max_tokens, **kwargs,
    )


async def complete_vision(
    prompt: str,
    image_path: Optional[str] = None,
    *,
    image_b64: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs: Any,
) -> Result[str]:
    """Vision completion: describe an image with a text prompt."""
    try:
        provider = _provider_for(model, "vision")
        if image_path is None and image_b64 is not None:
            import base64
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(base64.b64decode(image_b64))
            tmp.close()
            image_path = tmp.name
        if image_path is None:
            return Err(ValueError("complete_vision requires an image"))
        text = await asyncio.to_thread(provider.vision, image_path, prompt)
        return Ok(str(text))
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_router.complete_vision failed: %s", exc)
        return Err(exc)


def _extract_messages(messages: List[dict]) -> tuple[str, Optional[str]]:
    """Flatten chat messages into (prompt, image_path_or_None)."""
    texts: List[str] = []
    image_ref: Optional[str] = None
    for msg in messages or []:
        content = msg.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    texts.append(str(part.get("text", "")))
                elif part.get("type") == "image_url":
                    url = (part.get("image_url") or {}).get("url", "")
                    if url.startswith("data:image"):
                        import base64
                        import tempfile
                        header, _, b64 = url.partition(",")
                        ext = ".png" if "png" in header else ".jpg"
                        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                        tmp.write(base64.b64decode(b64))
                        tmp.close()
                        image_ref = tmp.name
    return "\n".join(t for t in texts if t), image_ref


def _wrap_response(text: str) -> SimpleNamespace:
    """LiteLLM-style response object: resp.choices[0].message.content."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(input_tokens=0, output_tokens=0),
    )


class LLMRouter:
    """Role-based router with a LiteLLM-compatible acompletion interface."""

    async def acompletion(self, model: str = "chat", messages: List[dict] | None = None,
                          prompt: str = "", timeout: int = 120, **kwargs: Any):
        """Route a request. `model` may be a role name, alias or provider/model ref."""
        prompt_text, image_ref = _extract_messages(messages) if messages else ("", None)
        if not prompt_text:
            prompt_text = prompt
        if image_ref is not None:
            result = await complete_vision(prompt_text, image_ref)
        else:
            role = MODEL_ALIASES.get(model, model)
            if role in ROLE_MODELS or role == "chat":
                role_for_provider = role if role in ("chat", "code", "vision",
                                                     "reasoning", "analysis") else "chat"
            else:
                # Looks like an explicit model ref (e.g. "ollama/qwen2.5:3b").
                role_for_provider = "chat"
                if "/" in model or ":" in model:
                    result = await complete_async(prompt_text, model=model, **kwargs)
                    if result.is_err():
                        raise result.unwrap()
                    return _wrap_response(result.unwrap())
            result = await complete_async(prompt_text, role=role_for_provider, **kwargs)
        if result.is_err():
            raise result.unwrap()
        return _wrap_response(result.unwrap())

    def completion(self, model: str = "chat", messages: List[dict] | None = None, **kwargs: Any):
        """Synchronous variant used by simple callers."""
        return asyncio.run(self.acompletion(model=model, messages=messages, **kwargs))


_router_instance: Optional[LLMRouter] = None
_router_lock = threading.Lock()


def get_router() -> LLMRouter:
    """Singleton router instance (LiteLLM-compatible surface)."""
    global _router_instance
    if _router_instance is None:
        with _router_lock:
            if _router_instance is None:
                _router_instance = LLMRouter()
    return _router_instance


def get_config_router() -> LLMRouter:
    """Alias for get_router kept for configuration-driven callers."""
    return get_router()


async def route_request(prompt: str, role: str = "chat", **kwargs: Any) -> str:
    """Route a request by role and return the response text (raises on failure)."""
    result = await complete_async(prompt, role=role, **kwargs)
    if result.is_err():
        raise result.unwrap()
    return result.unwrap()


__all__ = [
    "ROLE_MODELS", "MODEL_ALIASES", "MODEL_FALLBACKS",
    "complete", "complete_async", "complete_vision", "route_request",
    "get_router", "get_config_router", "get_ollama_url",
    "get_available_providers", "model_for_role", "LLMRouter",
]
