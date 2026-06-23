"""core/model_providers/gemini.py
Google Gemini provider implementation.
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator

import httpx

from core.model_providers.base import ModelProvider, ModelResult, ProviderStatus


class GeminiProvider(ModelProvider):
    name = "gemini"
    default_model = "gemini-2.0-flash"

    def __init__(self):
        super().__init__()
        self._base_url = "https://generativelanguage.googleapis.com/v1beta"
        self._models = ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-flash", "gemini-1.5-pro"]

    def _api_key(self) -> str:
        return self._get_credentials().get("api_key", "") or ""

    def _url(self, model: str, stream: bool = False) -> str:
        endpoint = "streamGenerateContent" if stream else "generateContent"
        return f"{self._base_url}/models/{model}:{endpoint}?key={self._api_key()}"

    async def generate(self, model: str, messages: list[dict[str, Any]], **kwargs) -> ModelResult:
        contents = self._convert_messages(messages)
        body = {"contents": contents}
        if "temperature" in kwargs:
            body["generationConfig"] = {"temperature": kwargs["temperature"]}
        if "max_tokens" in kwargs:
            body.setdefault("generationConfig", {})["maxOutputTokens"] = kwargs["max_tokens"]

        start = time.time()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self._url(model), json=body)
            resp.raise_for_status()
            data = resp.json()
        latency = (time.time() - start) * 1000
        candidates = data.get("candidates", [])
        content = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)
        return ModelResult(content=content, model=model, provider="gemini", latency_ms=latency)

    async def stream(self, model: str, messages: list[dict[str, Any]], **kwargs) -> AsyncIterator[str]:
        contents = self._convert_messages(messages)
        body = {"contents": contents}
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", self._url(model, stream=True), json=body) as resp:
                async for line in resp.aiter_lines():
                    if line.strip():
                        import json as _json
                        try:
                            chunk = _json.loads(line)
                            candidates = chunk.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for p in parts:
                                    if "text" in p:
                                        yield p["text"]
                        except _json.JSONDecodeError:
                            continue

    async def embeddings(self, model: str, input_text: str | list[str]) -> list[float]:
        texts = [input_text] if isinstance(input_text, str) else input_text
        embed_model = "text-embedding-004"
        body = {"model": f"models/{embed_model}", "content": {"parts": [{"text": texts[0]}]}}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self._base_url}/models/{embed_model}:embedContent?key={self._api_key()}", json=body)
            resp.raise_for_status()
            data = resp.json()
        return data.get("embedding", {}).get("values", [])

    async def vision(self, model: str, messages: list[dict[str, Any]], image_data: str, **kwargs) -> ModelResult:
        text = messages[-1]["content"] if messages else ""
        body = {
            "contents": [{
                "parts": [
                    {"text": text},
                    {"inline_data": {"mime_type": "image/png", "data": image_data}},
                ],
                "role": "user",
            }],
        }
        start = time.time()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self._url(model), json=body)
            resp.raise_for_status()
            data = resp.json()
        latency = (time.time() - start) * 1000
        candidates = data.get("candidates", [])
        content = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)
        return ModelResult(content=content, model=model, provider="gemini", latency_ms=latency)

    async def health_check(self) -> ProviderStatus:
        key = self._api_key()
        if not key:
            return ProviderStatus(available=False, healthy=False, error="No API key configured")
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self._base_url}/models?key={key}")
                latency = (time.time() - start) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["name"].replace("models/", "") for m in data.get("models", []) if "gemini" in m.get("name", "")]
                    return ProviderStatus(available=True, healthy=True, latency_ms=latency, models_available=models[:10])
                return ProviderStatus(available=True, healthy=False, error=f"HTTP {resp.status_code}")
        except Exception as e:
            return ProviderStatus(available=True, healthy=False, error=str(e))

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents = []
        for msg in messages:
            role = "model" if msg.get("role") == "assistant" else msg.get("role", "user")
            text = msg.get("content", "")
            if isinstance(text, list):
                text = " ".join(t.get("text", "") for t in text if isinstance(t, dict))
            contents.append({"parts": [{"text": str(text)}], "role": role})
        return contents
