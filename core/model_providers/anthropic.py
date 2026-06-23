"""core/model_providers/anthropic.py
Anthropic (Claude) provider implementation.
Wraps existing Anthropic call logic from core.llm_providers.
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator

import httpx

from core.model_providers.base import ModelProvider, ModelResult, ProviderStatus


ANTHROPIC_MODELS = [
    "claude-sonnet-4-20250514", "claude-sonnet-4", "claude-4-sonnet",
    "claude-3-5-sonnet-20241022", "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest", "claude-3-opus-latest",
    "claude-3-haiku-20240307",
]


class AnthropicProvider(ModelProvider):
    name = "anthropic"
    default_model = "claude-sonnet-4-20250514"

    def __init__(self):
        super().__init__()
        self._base_url = "https://api.anthropic.com/v1"
        self._models = ANTHROPIC_MODELS

    def _api_key(self) -> str:
        return self._get_credentials().get("api_key", "") or ""

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key(),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    async def generate(self, model: str, messages: list[dict[str, Any]], **kwargs) -> ModelResult:
        from core.llm_providers import _build_anthropic_payload, _parse_anthropic_response
        payload = _build_anthropic_payload(model, messages, **kwargs)
        start = time.time()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self._base_url}/messages", json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        latency = (time.time() - start) * 1000
        content = _parse_anthropic_response(data)
        tokens = data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
        return ModelResult(
            content=content, model=model, provider="anthropic",
            latency_ms=latency, tokens_used=tokens, raw=data,
        )

    async def stream(self, model: str, messages: list[dict[str, Any]], **kwargs) -> AsyncIterator[str]:
        from core.llm_providers import _build_anthropic_payload
        payload = _build_anthropic_payload(model, messages, stream=True, **kwargs)
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{self._base_url}/messages", json=payload, headers=self._headers()) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk_data = line[6:]
                        if chunk_data.strip() == "[DONE]":
                            break
                        import json as _json
                        try:
                            chunk = _json.loads(chunk_data)
                            if chunk.get("type") == "content_block_delta":
                                delta = chunk.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
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
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": image_data,
                }},
            ]}],
            "max_tokens": kwargs.get("max_tokens", 1024),
        }
        start = time.time()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self._base_url}/messages", json=body, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        latency = (time.time() - start) * 1000
        content = "".join(block.get("text", "") for block in data.get("content", []))
        return ModelResult(
            content=content, model=model, provider="anthropic", latency_ms=latency,
            tokens_used=data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0),
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
                    models = [m["id"] for m in data.get("data", []) if "claude" in m.get("id", "")]
                    return ProviderStatus(available=True, healthy=True, latency_ms=latency, models_available=models)
                return ProviderStatus(available=True, healthy=False, error=f"HTTP {resp.status_code}")
        except Exception as e:
            return ProviderStatus(available=True, healthy=False, error=str(e))
