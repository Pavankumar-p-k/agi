"""core/model_providers/ollama.py
Ollama provider implementation.
Wraps existing ollama call logic from core.llm_providers and core.llm_calls.
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator

import httpx

from core.model_providers.base import ModelProvider, ModelResult, ProviderStatus


# Maps configured model names to available Ollama model names.
# Add entries here when the system config references a model that doesn't exist locally.
_MODEL_ALIASES = {
    "qwen2.5-coder:3b": "qwen2.5:7b",
    "qwen2.5:3b": "qwen2.5:7b",
}

class OllamaProvider(ModelProvider):
    name = "ollama"
    default_model = _MODEL_ALIASES.get("qwen2.5-coder:3b", "qwen2.5-coder:3b")

    def __init__(self):
        super().__init__()
        from core.config_registry import config as _cfg
        self._base_url = _cfg.get("ollama.base_url", "http://localhost:11434")
        self._models = [
            "tinyllama", "deepseek-r1:1.5b", "qwen2.5:7b",
            "qwen3:4b", "qwen2.5:7b", "mistral:7b",
            "llama3.1:8b", "phi3:mini", "moondream:latest",
            "gemma4:e4b", "nomic-embed-text:latest",
        ]

    def _resolve_model(self, model: str) -> str:
        return _MODEL_ALIASES.get(model, model)

    async def generate(self, model: str, messages: list[dict[str, Any]], **kwargs) -> ModelResult:
        from core.llm_providers import _build_ollama_payload, _parse_ollama_response
        start = time.time()
        resolved = self._resolve_model(model)
        kwargs.setdefault("temperature", 0.7)
        kwargs.setdefault("max_tokens", 4096)
        payload = _build_ollama_payload(resolved, messages, **kwargs)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        latency = (time.time() - start) * 1000
        content = _parse_ollama_response(data)
        return ModelResult(
            content=content, model=model, provider="ollama",
            latency_ms=latency, tokens_used=data.get("eval_count", 0),
        )

    async def stream(self, model: str, messages: list[dict[str, Any]], **kwargs) -> AsyncIterator[str]:
        from core.llm_providers import _build_ollama_payload
        resolved = self._resolve_model(model)
        payload = _build_ollama_payload(resolved, messages, stream=True, **kwargs)
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{self._base_url}/api/chat", json=payload) as resp:
                async for line in resp.aiter_lines():
                    if line.strip():
                        import json as _json
                        try:
                            chunk = _json.loads(line)
                            if "message" in chunk and "content" in chunk["message"]:
                                yield chunk["message"]["content"]
                            if chunk.get("done"):
                                break
                        except _json.JSONDecodeError:
                            continue

    async def embeddings(self, model: str, input_text: str | list[str]) -> list[float]:
        texts = [input_text] if isinstance(input_text, str) else input_text
        embed_model = "nomic-embed-text:latest"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self._base_url}/api/embed", json={
                "model": embed_model, "input": texts,
            })
            resp.raise_for_status()
            data = resp.json()
        embeddings = data.get("embeddings", [])
        return embeddings[0] if embeddings else []

    async def vision(self, model: str, messages: list[dict[str, Any]], image_data: str, **kwargs) -> ModelResult:
        vision_model = model if "moondream" in model or "llava" in model else "moondream:latest"
        content = messages[-1]["content"] if messages else ""
        payload = {
            "model": vision_model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": content},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
            ]}],
            "stream": False,
        }
        start = time.time()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        latency = (time.time() - start) * 1000
        return ModelResult(
            content=data.get("message", {}).get("content", ""),
            model=vision_model, provider="ollama", latency_ms=latency,
        )

    async def health_check(self) -> ProviderStatus:
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                latency = (time.time() - start) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    return ProviderStatus(
                        available=True, healthy=True,
                        latency_ms=latency, models_available=models,
                    )
                return ProviderStatus(available=False, healthy=False, error=f"HTTP {resp.status_code}")
        except Exception as e:
            return ProviderStatus(available=False, healthy=False, error=str(e))
