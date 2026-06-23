"""core/model_providers/openrouter.py
OpenRouter provider implementation.
OpenAI-compatible API at openrouter.ai.
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator

import httpx

from core.model_providers.base import ModelProvider, ModelResult, ProviderStatus


class OpenRouterProvider(ModelProvider):
    name = "openrouter"
    default_model = "openai/gpt-4o"

    def __init__(self):
        super().__init__()
        self._base_url = "https://openrouter.ai/api/v1"
        self._models = [
            "openai/gpt-4o", "openai/gpt-4o-mini", "anthropic/claude-sonnet-4",
            "google/gemini-2.0-flash", "meta-llama/llama-3.1-70b-instruct",
            "deepseek/deepseek-r1", "mistralai/mixtral-8x22b-instruct",
            "qwen/qwen-2.5-72b-instruct",
        ]

    def _api_key(self) -> str:
        return self._get_credentials().get("api_key", "") or ""

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://jarvis.ai",
            "X-Title": "JARVIS",
        }

    async def generate(self, model: str, messages: list[dict[str, Any]], **kwargs) -> ModelResult:
        body = {"model": model, "messages": messages}
        if "temperature" in kwargs:
            body["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            body["max_tokens"] = kwargs["max_tokens"]

        start = time.time()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self._base_url}/chat/completions", json=body, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        latency = (time.time() - start) * 1000
        content = data["choices"][0]["message"].get("content", "")
        return ModelResult(
            content=content, model=model, provider="openrouter",
            latency_ms=latency, tokens_used=data.get("usage", {}).get("total_tokens", 0),
        )

    async def stream(self, model: str, messages: list[dict[str, Any]], **kwargs) -> AsyncIterator[str]:
        body = {"model": model, "messages": messages, "stream": True}
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{self._base_url}/chat/completions", json=body, headers=self._headers()) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk_data = line[6:]
                        if chunk_data.strip() == "[DONE]":
                            break
                        import json as _json
                        try:
                            chunk = _json.loads(chunk_data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                        except _json.JSONDecodeError:
                            continue

    async def embeddings(self, model: str, input_text: str | list[str]) -> list[float]:
        return []

    async def vision(self, model: str, messages: list[dict[str, Any]], image_data: str, **kwargs) -> ModelResult:
        content = messages[-1]["content"] if messages else ""
        body = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": content},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
            ]}],
        }
        start = time.time()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self._base_url}/chat/completions", json=body, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        latency = (time.time() - start) * 1000
        return ModelResult(
            content=data["choices"][0]["message"]["content"],
            model=model, provider="openrouter", latency_ms=latency,
        )

    async def health_check(self) -> ProviderStatus:
        key = self._api_key()
        if not key:
            return ProviderStatus(available=False, healthy=False, error="No API key configured")
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self._base_url}/models", headers=self._headers())
                latency = (time.time() - start) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["id"] for m in data.get("data", [])]
                    return ProviderStatus(available=True, healthy=True, latency_ms=latency, models_available=models[:20])
                return ProviderStatus(available=True, healthy=False, error=f"HTTP {resp.status_code}")
        except Exception as e:
            return ProviderStatus(available=True, healthy=False, error=str(e))
