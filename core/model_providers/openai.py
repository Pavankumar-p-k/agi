"""core/model_providers/openai.py
OpenAI provider implementation.
Wraps existing OpenAI call logic from core.llm_providers.
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator

import httpx

from core.model_providers.base import ModelProvider, ModelResult, ProviderStatus


class OpenAIProvider(ModelProvider):
    name = "openai"
    default_model = "gpt-4o"

    def __init__(self):
        super().__init__()
        self._base_url = "https://api.openai.com/v1"
        self._models = [
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
            "o1", "o3", "o4-mini", "gpt-4.1", "gpt-4.1-mini",
        ]

    def _api_key(self) -> str:
        return self._get_credentials().get("api_key", "") or ""

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

    async def generate(self, model: str, messages: list[dict[str, Any]], **kwargs) -> ModelResult:
        from core.llm_providers import _uses_max_completion_tokens, _restricts_temperature
        body: dict[str, Any] = {"model": model, "messages": messages}
        if "temperature" in kwargs and not _restricts_temperature(model):
            body["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            if _uses_max_completion_tokens(model):
                body["max_completion_tokens"] = kwargs["max_tokens"]
            else:
                body["max_tokens"] = kwargs["max_tokens"]
        if "response_format" in kwargs:
            body["response_format"] = kwargs["response_format"]

        start = time.time()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self._base_url}/chat/completions", json=body, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        latency = (time.time() - start) * 1000
        choice = data["choices"][0]
        content = choice["message"].get("content", "")
        return ModelResult(
            content=content, model=model, provider="openai",
            latency_ms=latency, tokens_used=data.get("usage", {}).get("total_tokens", 0),
            raw=data,
        )

    async def stream(self, model: str, messages: list[dict[str, Any]], **kwargs) -> AsyncIterator[str]:
        from core.llm_providers import _uses_max_completion_tokens, _restricts_temperature
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if "temperature" in kwargs and not _restricts_temperature(model):
            body["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            body["max_tokens"] = kwargs["max_tokens"]

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
        texts = [input_text] if isinstance(input_text, str) else input_text
        embed_model = "text-embedding-3-small"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self._base_url}/embeddings", json={
                "model": embed_model, "input": texts,
            }, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        return data["data"][0]["embedding"]

    async def vision(self, model: str, messages: list[dict[str, Any]], image_data: str, **kwargs) -> ModelResult:
        content = messages[-1]["content"] if messages else ""
        body = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": content},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
            ]}],
            "max_tokens": kwargs.get("max_tokens", 1024),
        }
        start = time.time()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self._base_url}/chat/completions", json=body, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        latency = (time.time() - start) * 1000
        return ModelResult(
            content=data["choices"][0]["message"]["content"],
            model=model, provider="openai", latency_ms=latency,
            tokens_used=data.get("usage", {}).get("total_tokens", 0),
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
                    models = [m["id"] for m in data.get("data", []) if "gpt" in m["id"] or "o1" in m["id"] or "o3" in m["id"]]
                    return ProviderStatus(available=True, healthy=True, latency_ms=latency, models_available=models[:20])
                return ProviderStatus(available=True, healthy=False, error=f"HTTP {resp.status_code}")
        except Exception as e:
            return ProviderStatus(available=True, healthy=False, error=str(e))
