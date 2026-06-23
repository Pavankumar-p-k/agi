"""core/model_providers/groq.py
Groq provider implementation.
OpenAI-compatible API at groq.com.
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator

import httpx

from core.model_providers.base import ModelProvider, ModelResult, ProviderStatus


class GroqProvider(ModelProvider):
    name = "groq"
    default_model = "llama3-70b-8192"

    def __init__(self):
        super().__init__()
        self._base_url = "https://api.groq.com/openai/v1"
        self._models = [
            "llama3-70b-8192", "llama3-8b-8192", "mixtral-8x7b-32768",
            "gemma2-9b-it", "deepseek-r1-distill-llama-70b",
        ]

    def _api_key(self) -> str:
        return self._get_credentials().get("api_key", "") or ""

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
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
            content=content, model=model, provider="groq",
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
        return await self.generate(model, messages, **kwargs)

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
                    return ProviderStatus(available=True, healthy=True, latency_ms=latency, models_available=models)
                return ProviderStatus(available=True, healthy=False, error=f"HTTP {resp.status_code}")
        except Exception as e:
            return ProviderStatus(available=True, healthy=False, error=str(e))
