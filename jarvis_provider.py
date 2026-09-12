#!/usr/bin/env python3
"""
JARVIS UNIFIED TOP-LEVEL PROVIDER
=================================
Single source of truth for ALL models and API keys across every module.

USER CONFIGURES EVERYTHING HERE (via .env / .env.local):
  # Model roles (format: provider/model-id)
  CHAT_MODEL=ollama/qwen3:4b
  CODE_MODEL=ollama/qwen2.5-coder:3b
  VISION_MODEL=ollama/llava:7b
  REASONING_MODEL=ollama/deepseek-r1:1.5b
  EMBEDDING_MODEL=nomic-embed-text
  # Cloud API keys (uncomment to enable that provider)
  OPENAI_API_KEY=...
  ANTHROPIC_API_KEY=...
  GEMINI_API_KEY=...
  GROQ_API_KEY=...
  OPENROUTER_API_KEY=...
  DEEPSEEK_API_KEY=...

Any module calls get_provider("chat") or get_provider("vision") and gets the
right model. After the build you simply fill in cloud keys in .env — NO code
changes anywhere. Ollama is the default for local testing.

USAGE:
    from jarvis_provider import get_provider, get_model, list_providers
    llm = get_provider("chat")
    text = llm.chat("hello")
"""
from __future__ import annotations
import os
import json
import requests
from pathlib import Path
from abc import ABC, abstractmethod

ROOT = Path(__file__).resolve().parent

# ---------- .env LOADER (no extra dep; we avoid python-dotenv if missing) ----------
def _load_dotenv(paths=None):
    if paths is None:
        # Load shared defaults first, then let machine-local settings override
        # them. Existing process environment variables remain authoritative.
        paths = [ROOT / ".env", ROOT / ".env.local"]
    process_keys = set(os.environ)
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in process_keys:
                    os.environ[key] = value
        except Exception:
            continue

_load_dotenv()


def _env(name, default=None):
    return os.getenv(name, default)


# ---------- ABSTRACT PROVIDER ----------
class LLMProvider(ABC):
    provider_id: str = "base"
    supports_vision: bool = False
    supports_chat: bool = True

    @abstractmethod
    def chat(self, prompt: str, temperature: float = 0.1, max_tokens: int | None = None) -> str:
        """Single-turn text completion for a prompt."""

    def vision(self, image_path: str, prompt: str = "Describe what you see in detail.") -> str:
        raise NotImplementedError(f"{self.provider_id} does not support vision")


# ---------- OLLAMA (default, local testing) ----------
class OllamaLLM(LLMProvider):
    provider_id = "ollama"
    supports_vision = True

    def __init__(self, model: str = "qwen2.5-coder:3b", url: str = "http://localhost:11434"):
        self.model = model
        self.url = url.rstrip("/")
        # Detect vision model: explicit OLLAMA_VISION_MODEL, else VISION_MODEL, else this model.
        vision_ref = _env("OLLAMA_VISION_MODEL") or _env("VISION_MODEL") or f"ollama/{model}"
        _, _, vmodel = vision_ref.partition("/")
        self._vision_model = vmodel or model

    def _generate(self, model, prompt, temperature, images=None, timeout=None):
        timeout = float(_env("OLLAMA_REQUEST_TIMEOUT", "90")) if timeout is None else timeout
        payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": temperature}}
        if images:
            payload["images"] = images
        resp = requests.post(f"{self.url}/api/generate", json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["response"]

    def chat(self, prompt, temperature=0.1, max_tokens=None):
        return self._generate(self.model, prompt, temperature)

    def vision(self, image_path, prompt="Describe what you see in detail."):
        """Ollama /api/generate expects images as base64 strings."""
        import base64
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return self._generate(self._vision_model, prompt, 0.1, images=[b64])


# ---------- OPENAI-COMPATIBLE ----------
class OpenAILLM(LLMProvider):
    provider_id = "openai"
    supports_vision = True

    def __init__(self, api_key=None, model=None, base_url="https://api.openai.com/v1"):
        self.api_key = api_key or _env("OPENAI_API_KEY")
        self.model = model or _env("OPENAI_MODEL", "gpt-4o")
        self.base_url = base_url.rstrip("/")
        self._vision_model = _env("OPENAI_VISION_MODEL", self.model)
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

    def _chat(self, model, prompt, temperature, image_path=None):
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        content = [{"type": "text", "text": prompt}]
        if image_path:
            import base64
            b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
        body = {"model": model, "temperature": temperature, "messages": [{"role": "user", "content": content}]}
        resp = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=body, timeout=240)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def chat(self, prompt, temperature=0.1, max_tokens=None):
        return self._chat(self.model, prompt, temperature)

    def vision(self, image_path, prompt="Describe what you see in detail."):
        return self._chat(self._vision_model, prompt, 0.1, image_path=image_path)


# ---------- ANTHROPIC ----------
class AnthropicLLM(LLMProvider):
    provider_id = "anthropic"
    supports_vision = True

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or _env("ANTHROPIC_API_KEY")
        self.model = model or _env("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

    def chat(self, prompt, temperature=0.1, max_tokens=None):
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        body = {"model": self.model, "max_tokens": max_tokens or 4096, "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}]}
        resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=240)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    def vision(self, image_path, prompt="Describe what you see in detail."):
        import base64
        media_type = "image/png"
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        body = {"model": self.model, "max_tokens": 4096,
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": prompt}]}]}
        resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=240)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


# ---------- GEMINI ----------
class GeminiLLM(LLMProvider):
    provider_id = "gemini"
    supports_vision = True

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or _env("GEMINI_API_KEY")
        self.model = model or _env("GEMINI_MODEL", "gemini-2.0-flash")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

    def chat(self, prompt, temperature=0.1, max_tokens=None):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = requests.post(url, json=body, timeout=240)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    def vision(self, image_path, prompt="Describe what you see in detail."):
        import base64
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        body = {"contents": [{"parts": [
            {"inline_data": {"mime_type": "image/png", "data": b64}},
            {"text": prompt}]}]}
        resp = requests.post(url, json=body, timeout=240)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


# ---------- GROQ ----------
class GroqLLM(LLMProvider):
    provider_id = "groq"
    supports_vision = False

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or _env("GROQ_API_KEY")
        self.model = model or _env("GROQ_MODEL", "llama-3.3-70b-versatile")
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY not set")

    def chat(self, prompt, temperature=0.1, max_tokens=None):
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {"model": self.model, "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}]}
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body, timeout=240)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# ---------- OPENROUTER ----------
class OpenRouterLLM(LLMProvider):
    provider_id = "openrouter"
    supports_vision = False

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or _env("OPENROUTER_API_KEY")
        self.model = model or _env("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        self.base_url = _env(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).rstrip("/")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")

    def chat(self, prompt, temperature=0.1, max_tokens=None):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": _env("OPENROUTER_SITE_URL", "http://localhost"),
            "X-Title": _env("OPENROUTER_APP_NAME", "JARVIS"),
        }
        body = {
            "model": self.model,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=body,
            timeout=240,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# ---------- MODEL FACTORY / REGISTRY ----------
_PROVIDER_CLASSES = {
    "ollama": OllamaLLM,
    "openai": OpenAILLM,
    "anthropic": AnthropicLLM,
    "gemini": GeminiLLM,
    "groq": GroqLLM,
    "openrouter": OpenRouterLLM,
}


def _parse_model_ref(ref: str) -> tuple[str, str]:
    """'provider/model-id' -> (provider, model)"""
    if "/" in ref:
        prov, _, model = ref.partition("/")
        return prov.strip().lower(), model.strip()
    return "ollama", ref.strip()


def _build(provider_id: str, model: str) -> LLMProvider:
    cls = _PROVIDER_CLASSES.get(provider_id)
    if cls is None:
        # try aliases
        aliases = {"codex": "openai", "gpt": "openai", "claude": "anthropic", "deepseek": "openai",
                   "ollama": "ollama", "mistral": "openai", "together": "openai", "fireworks": "openai",
                   "nvidia": "openai", "xai": "openai"}
        provider_id = aliases.get(provider_id, provider_id)
        cls = _PROVIDER_CLASSES.get(provider_id)
        if cls is None:
            raise RuntimeError(f"Unknown/disabled provider: {provider_id}. Set its API key in .env to enable it.")
    try:
        return cls(model=model)
    except RuntimeError as e:
        raise RuntimeError(f"Provider '{provider_id}' not enabled: {e}")


# The single registry every module reads from.
_MODEL_CACHE: dict[str, LLMProvider] = {}


def get_provider(role: str = "chat") -> LLMProvider:
    """Get the configured model for a ROLE (chat|code|vision|reasoning|analysis|embedding...).
    Reads CHAT_MODEL / CODE_MODEL / VISION_MODEL / ... from .env, defaults to Ollama."""
    role_key = f"{role.upper()}_MODEL"
    ref = _env(role_key)
    if not ref:
        # fallback map
        fallback = {
            "chat": _env("CHAT_MODEL", "ollama/qwen2.5-coder:3b"),
            "code": _env("CODE_MODEL", "ollama/qwen2.5-coder:3b"),
            "vision": _env("VISION_MODEL", "ollama/llava:7b"),
            "reasoning": _env("REASONING_MODEL", "ollama/qwen2.5-coder:3b"),
            "analysis": _env("ANALYSIS_MODEL", "ollama/qwen2.5-coder:3b"),
            "embedding": _env("EMBEDDING_MODEL", "nomic-embed-text"),
        }
        ref = fallback.get(role, "ollama/qwen2.5-coder:3b")

    if ref in _MODEL_CACHE:
        return _MODEL_CACHE[ref]

    provider_id, model = _parse_model_ref(ref)
    try:
        provider = _build(provider_id, model)
    except RuntimeError as e:
        # Explicit cloud configuration must fail visibly; otherwise a missing
        # key silently routes long-task reasoning back to the small local model.
        if provider_id != "ollama" and _env(role_key):
            raise
        print(f"[jarvis_provider] WARNING: {e} — falling back to Ollama for role '{role}'")
        provider = OllamaLLM(model=_env("OLLAMA_MODEL", "qwen2.5-coder:3b"))
    _MODEL_CACHE[ref] = provider
    return provider


def get_model(role: str = "chat") -> str:
    """Return the model-id string configured for a role."""
    return _env(f"{role.upper()}_MODEL") or {
        "chat": _env("CHAT_MODEL", "ollama/qwen2.5-coder:3b"),
        "code": _env("CODE_MODEL", "ollama/qwen2.5-coder:3b"),
        "vision": _env("VISION_MODEL", "ollama/llava:7b"),
        "reasoning": _env("REASONING_MODEL", "ollama/qwen2.5-coder:3b"),
    }.get(role, "ollama/qwen2.5-coder:3b")


def list_models() -> dict:
    """Show what roles map to what models (for the user to configure)."""
    roles = ["chat", "code", "vision", "reasoning", "analysis", "embedding"]
    out = {}
    for r in roles:
        out[r] = get_model(r)
    enabled = {pid: bool(_env(f"{pid.upper()}_API_KEY")) for pid in _PROVIDER_CLASSES if pid != "ollama"}
    return {"models": out, "cloud_providers_enabled": enabled}
